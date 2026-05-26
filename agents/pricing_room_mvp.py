import asyncio
import os
import json
import glob
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=-6))
from agents.llm_client import call_claude
from agents.brain import load_system_prompt
import agents.etsy_client as etsy_client
import httpx

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
PRICING_DIR = os.path.join(BRAIN_PATH, "rooms", "pricing", "reports")
SHOPIFY_API_VERSION = "2024-04"

_PRICING_FALLBACK = """You are the Pricing Agent for a print-on-demand store selling on both Shopify and Etsy.
Analyse the products and competitor intelligence provided. Give clear, actionable pricing recommendations.
Rules:
- T-shirt base cost ~$13, hoodie ~$23, long sleeve ~$15, crewneck ~$18, mug ~$6, tote ~$10, tumbler ~$15, sticker ~$4, hat ~$19, apron ~$20. Never recommend below base cost + 40% margin.
- Round all prices to .99 (e.g. $24.99, $29.99).
- If competitors charge 15%+ more, recommend RAISE.
- If a product has zero sales and has been live 14+ days, recommend LOWER by $3-5 as a test.
- Otherwise KEEP.
- Be specific: give exact recommended price per product.
- Keep each product note to one sentence.
- End with a 2-3 sentence overall pricing strategy summary."""


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


async def apply_etsy_price_change(listing_id: int, new_price: float) -> dict:
    return await etsy_client.update_listing_price(listing_id, new_price)


def _parse_etsy_price(price_data) -> float:
    """Etsy returns price as {amount, divisor} or a plain float."""
    if isinstance(price_data, dict):
        divisor = price_data.get("divisor") or 100
        return price_data.get("amount", 0) / divisor
    return float(price_data or 0)


async def _fetch_etsy_listings() -> list:
    if not etsy_client.is_configured():
        return []
    return await etsy_client.fetch_listings(state="active", limit=250)


async def _fetch_etsy_receipts() -> list:
    if not etsy_client.is_configured():
        return []
    return await etsy_client.fetch_receipts(limit=250)


def _build_etsy_product_stats(listings: list, receipts: list) -> list:
    # Build sales map: listing_id -> {units_sold, last_sale_ts}
    sales: dict[int, dict] = {}
    for receipt in receipts:
        if not receipt.get("was_paid"):
            continue
        sale_ts = receipt.get("create_timestamp") or receipt.get("created_timestamp") or 0
        for tx in receipt.get("transactions", []):
            lid = tx.get("listing_id")
            if lid is None:
                continue
            if lid not in sales:
                sales[lid] = {"units_sold": 0, "last_sale_ts": 0}
            sales[lid]["units_sold"] += tx.get("quantity", 1)
            if sale_ts > sales[lid]["last_sale_ts"]:
                sales[lid]["last_sale_ts"] = sale_ts

    now = datetime.now(timezone.utc)
    result = []
    for listing in listings:
        lid = listing.get("listing_id")
        stat = sales.get(lid, {"units_sold": 0, "last_sale_ts": 0})
        price = _parse_etsy_price(listing.get("price", 0))
        created_ts = listing.get("original_creation_timestamp") or listing.get("creation_timestamp") or 0
        days_live = int((now.timestamp() - created_ts) / 86400) if created_ts else None
        last_sale_ts = stat["last_sale_ts"]
        days_since_sale = int((now.timestamp() - last_sale_ts) / 86400) if last_sale_ts else None

        result.append({
            "listing_id": lid,
            "title": listing.get("title", ""),
            "price": price,
            "units_sold": stat["units_sold"],
            "days_live": days_live,
            "days_since_sale": days_since_sale,
            "views": listing.get("views", 0),
        })

    result.sort(key=lambda x: -x["units_sold"])
    return result


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


async def _run_analysis(
    product_stats: list,
    market_intel: str,
    etsy_stats: list | None = None,
) -> tuple[str, str]:
    if not product_stats and not etsy_stats:
        return "No active products to analyse.", "none"

    def _last_sale(p: dict) -> str:
        return f"{p['days_since_sale']}d ago" if p["days_since_sale"] is not None else "never"

    shopify_text = "\n".join(
        f"- [Shopify] \"{p['title']}\" | ${p['price']:.2f} | "
        f"{p['units_sold']} sold | {p['days_live'] or '?'}d live | last sale: {_last_sale(p)}"
        for p in product_stats
    ) or "- None"

    etsy_lines = ""
    if etsy_stats:
        etsy_lines = "\n\nETSY LISTINGS:\n" + "\n".join(
            f"- [Etsy] \"{p['title']}\" | ${p['price']:.2f} | "
            f"{p['units_sold']} sold | {p['days_live'] or '?'}d live | last sale: {_last_sale(p)} | {p['views']} views"
            for p in etsy_stats
        )

    prompt = f"""Analyse pricing for these active print-on-demand products on Shopify and Etsy:

SHOPIFY PRODUCTS:
{shopify_text}{etsy_lines}

MARKET INTELLIGENCE:
{market_intel or 'No live data available — use general POD pricing knowledge.'}

For each product give:
- Platform (Shopify / Etsy)
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

    shopify_md = "\n".join(
        f"- {p['title']} | ${p['price']:.2f} | {p['units_sold']} sold | "
        f"{p['days_live'] or '?'}d live"
        for p in data.get("product_stats", [])
    ) or "- No active products"

    etsy_section = ""
    if data.get("etsy_product_stats"):
        etsy_md = "\n".join(
            f"- {p['title']} | ${p['price']:.2f} | {p['units_sold']} sold | "
            f"{p['days_live'] or '?'}d live | {p['views']} views"
            for p in data["etsy_product_stats"]
        )
        etsy_section = f"\n## Etsy Listings\n{etsy_md}\n"

    md = f"""# Pricing Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

## Shopify Products
{shopify_md}
{etsy_section}
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

    # Fetch all data sources in parallel
    orders_task         = asyncio.create_task(_fetch_orders())
    etsy_listings_task  = asyncio.create_task(_fetch_etsy_listings())
    etsy_receipts_task  = asyncio.create_task(_fetch_etsy_receipts())
    market_intel_task   = asyncio.create_task(_gather_market_intel())

    orders = []
    try:
        orders = await orders_task
    except Exception as e:
        print(f"[pricing] Shopify orders fetch failed (continuing): {e}")

    etsy_listings, etsy_receipts = [], []
    try:
        etsy_listings = await etsy_listings_task
        etsy_receipts = await etsy_receipts_task
    except Exception as e:
        print(f"[pricing] Etsy fetch failed (continuing): {e}")

    market_intel = await market_intel_task

    product_stats = _build_product_stats(products, orders)
    etsy_stats    = _build_etsy_product_stats(etsy_listings, etsy_receipts)

    analysis, model_used = await _run_analysis(product_stats, market_intel, etsy_stats)

    data = {
        "run_date":               datetime.now(_CST).strftime("%Y-%m-%d"),
        "products_analysed":      len(product_stats),
        "etsy_listings_analysed": len(etsy_stats),
        "product_stats":          product_stats,
        "etsy_product_stats":     etsy_stats,
        "market_intel":           market_intel,
        "analysis":               analysis,
        "model_used":             model_used,
    }

    data["report_path"] = _save_report(data)
    return data
