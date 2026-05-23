import asyncio
import os
import json
import glob
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=-6))
from agents.llm_client import call_claude
from agents.brain import load_system_prompt
import httpx

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
PRICING_DIR = os.path.join(BRAIN_PATH, "rooms", "pricing", "reports")
SHOPIFY_API_VERSION = "2025-01"

_PRICING_FALLBACK = """You are the Pricing Agent for a print-on-demand Shopify store.
Analyse the products and competitor intelligence provided. Give clear, actionable pricing recommendations.
Rules:
- T-shirt base cost ~$12, hoodie base cost ~$22. Never recommend below base cost + 40% margin.
- Round all prices to .99 (e.g. $24.99, $29.99).
- If competitors charge 15%+ more, recommend RAISE.
- If a product has zero sales and has been live 14+ days, recommend LOWER by $3-5 as a test.
- Otherwise KEEP.
- Be specific: give exact recommended price per product.
- Keep each product note to one sentence.
- End with a 2-3 sentence overall strategy summary."""


def _shopify_headers() -> dict:
    return {
        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _shopify_url(path: str) -> str:
    store = os.getenv("SHOPIFY_STORE_URL", "")
    return f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/{path}"


async def _fetch_products() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _shopify_url("products.json?limit=250&status=active"),
            headers=_shopify_headers(),
        )
        r.raise_for_status()
        return r.json().get("products", [])


async def _fetch_orders() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _shopify_url("orders.json?limit=250&status=any"),
            headers=_shopify_headers(),
        )
        r.raise_for_status()
        return r.json().get("orders", [])


async def apply_price_change(variant_id: int, new_price: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.put(
            _shopify_url(f"variants/{variant_id}.json"),
            headers=_shopify_headers(),
            json={"variant": {"id": variant_id, "price": new_price}},
        )
        r.raise_for_status()
        return r.json().get("variant", {})


def _build_product_stats(products: list, orders: list) -> list:
    sales: dict[int, dict] = {}
    for order in orders:
        if order.get("financial_status") not in ("paid", "partially_paid"):
            continue
        for item in order.get("line_items", []):
            pid = item.get("product_id")
            if pid is None:
                continue
            if pid not in sales:
                sales[pid] = {"units_sold": 0, "last_sale": None}
            sales[pid]["units_sold"] += item.get("quantity", 0)
            created = order.get("created_at", "")[:10]
            prev = sales[pid]["last_sale"]
            if prev is None or created > prev:
                sales[pid]["last_sale"] = created

    now = datetime.now(timezone.utc).date()
    result = []
    for p in products:
        pid = p["id"]
        stat = sales.get(pid, {"units_sold": 0, "last_sale": None})
        variant = p["variants"][0] if p.get("variants") else {}
        price = float(variant.get("price") or 0)
        variant_id = variant.get("id")
        created_date = p.get("created_at", "")[:10]
        days_live = (now - datetime.fromisoformat(created_date).date()).days if created_date else None
        last_sale = stat["last_sale"]
        days_since_sale = (now - datetime.fromisoformat(last_sale).date()).days if last_sale else None

        result.append({
            "id": pid,
            "variant_id": variant_id,
            "title": p["title"],
            "price": price,
            "units_sold": stat["units_sold"],
            "days_live": days_live,
            "days_since_sale": days_since_sale,
            "last_sale": last_sale,
        })

    result.sort(key=lambda x: -x["units_sold"])
    return result


def _search_competitor_prices() -> str:
    try:
        from ddgs import DDGS
        client = DDGS()
        queries = [
            f"print on demand t-shirt pricing etsy best selling {datetime.now().strftime('%Y')}",
            "graphic tee price range print on demand profit margin 2025 2026",
            "etsy t-shirt hoodie average selling price competitor analysis",
        ]
        lines = ["=== Competitor Price Intelligence (DuckDuckGo) ==="]
        for q in queries:
            results = client.text(q, max_results=2)
            for r in results or []:
                snippet = (r.get("body") or "").strip()
                if snippet:
                    lines.append(f"- {snippet[:350]}")
        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception as e:
        print(f"[pricing] DDG search failed: {e}")
        return ""


async def _gather_market_intel() -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _search_competitor_prices)


async def _run_analysis(product_stats: list, market_intel: str) -> tuple[str, str]:
    if not product_stats:
        return "No active products to analyse.", "none"

    products_text = "\n".join(
        f"- \"{p['title']}\" | current price: ${p['price']:.2f} | "
        f"units sold: {p['units_sold']} | "
        f"days live: {p['days_live'] or 'unknown'} | "
        f"days since last sale: {p['days_since_sale'] if p['days_since_sale'] is not None else 'never sold'}"
        for p in product_stats
    )

    prompt = f"""Analyse pricing for these active Shopify print-on-demand products:

PRODUCTS:
{products_text}

MARKET INTELLIGENCE:
{market_intel or 'No live data available — use general POD pricing knowledge.'}

For each product give:
- Action: RAISE / LOWER / KEEP
- Recommended price (if changing)
- One-sentence reason

Then give a 2-3 sentence overall pricing strategy summary."""

    system = load_system_prompt("pricing", "pricing", _PRICING_FALLBACK)
    try:
        text = await call_claude(prompt, system=system, room="pricing")
        return text, "claude"
    except Exception:
        text = await call_claude(prompt, system=system, room="pricing")
        return text, "claude"


def _save_report(data: dict) -> str:
    os.makedirs(PRICING_DIR, exist_ok=True)

    latest_path = os.path.join(PRICING_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(PRICING_DIR, f"pricing_{ts}.md")

    products_md = "\n".join(
        f"- {p['title']} | ${p['price']:.2f} | {p['units_sold']} sold | "
        f"{p['days_live'] or '?'}d live"
        for p in data.get("product_stats", [])
    ) or "- No active products"

    md = f"""# Pricing Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

## Products Analysed
{products_md}

## Pricing Recommendations
{data.get('analysis', '')}

---
Model: {data.get('model_used', '—')}
"""
    with open(md_path, "w") as f:
        f.write(md)

    return md_path


async def get_latest_report() -> dict | None:
    path = os.path.join(PRICING_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_pricing() -> dict:
    try:
        products = await _fetch_products()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        msg = "Shopify token expired — refresh it in rooms/captain/shopify-token.md" if status == 401 else f"Shopify API error {status}"
        return {"error": msg, "shopify_error": True}
    except Exception as e:
        return {"error": f"Shopify products fetch failed: {e}", "shopify_error": True}

    try:
        orders = await _fetch_orders()
    except Exception as e:
        orders = []
        print(f"[pricing] Orders fetch failed (continuing): {e}")

    product_stats = _build_product_stats(products, orders)
    market_intel = await _gather_market_intel()
    analysis, model_used = await _run_analysis(product_stats, market_intel)

    data = {
        "run_date": datetime.now(_CST).strftime("%Y-%m-%d"),
        "products_analysed": len(product_stats),
        "product_stats": product_stats,
        "market_intel": market_intel,
        "analysis": analysis,
        "model_used": model_used,
    }

    data["report_path"] = _save_report(data)
    return data
