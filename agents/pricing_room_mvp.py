import asyncio
import json
import os
from datetime import datetime

import httpx

from agents.brain import load_system_prompt
from agents.llm_client import call_claude, call_local

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
PRICING_DIR = os.path.join(BRAIN_PATH, "rooms", "pricing", "reports")
SHOPIFY_API_VERSION = "2025-01"

# Approximate Printify base costs per product type (USD)
PRINTIFY_BASE_COSTS: dict[str, float] = {
    "Unisex T-Shirt": 13.50,
    "Hoodie": 22.00,
    "Long Sleeve T-Shirt": 16.50,
}
DEFAULT_BASE_COST = 14.00
TARGET_MARGIN = 0.45  # 45% minimum margin
SHOPIFY_FEE_PCT = 0.029  # 2.9% + $0.30 per transaction (Shopify Payments)
SHOPIFY_FEE_FLAT = 0.30

_PRICING_FALLBACK = """You are the Pricing Agent for a print-on-demand Shopify store.
Analyze the provided product prices, margins, and competitor market data.
For each product, assess:
- Whether the current price is competitive vs market
- Whether margin is healthy (target: 45%+ after production + Shopify fees)
- Specific price adjustment recommendations (up, down, or hold)
Flag any products priced dangerously below cost or well above market.
Output a concise markdown report. Be specific with numbers. 200 words max."""

DDG_PRICING_QUERIES = [
    "print on demand t-shirt price shopify etsy 2025 how much charge",
    "print on demand hoodie retail price average 2025",
    "competitive pricing print on demand apparel profit margin 2025",
]


def _shopify_headers() -> dict:
    return {
        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _shopify_url(path: str) -> str:
    store = os.getenv("SHOPIFY_STORE_URL", "")
    return f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/{path}"


async def _fetch_shopify_products() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _shopify_url("products.json?limit=250&status=any"),
            headers=_shopify_headers(),
        )
        r.raise_for_status()
        return r.json().get("products", [])


async def _apply_shopify_price(product_id: int, variant_id: int, new_price: str) -> bool:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.put(
            _shopify_url(f"variants/{variant_id}.json"),
            headers=_shopify_headers(),
            json={"variant": {"id": variant_id, "price": new_price}},
        )
        return r.status_code == 200


def _detect_product_type(title: str) -> str:
    lower = title.lower()
    if "hoodie" in lower or "sweatshirt" in lower:
        return "Hoodie"
    if "long sleeve" in lower or "longsleeve" in lower:
        return "Long Sleeve T-Shirt"
    return "Unisex T-Shirt"


def _calc_margin(price: float, base_cost: float) -> float:
    if price <= 0:
        return 0.0
    net = price - base_cost - (price * SHOPIFY_FEE_PCT) - SHOPIFY_FEE_FLAT
    return round(net / price, 4)


def _suggested_price(base_cost: float) -> float:
    # Solve for price where margin = TARGET_MARGIN after Shopify fee
    # net = price - base_cost - price*fee_pct - fee_flat = price * margin
    # price*(1 - fee_pct - margin) = base_cost + fee_flat
    denominator = 1 - SHOPIFY_FEE_PCT - TARGET_MARGIN
    raw = (base_cost + SHOPIFY_FEE_FLAT) / denominator
    # Round up to nearest .99
    import math
    return math.ceil(raw) - 0.01


def _build_product_analysis(products: list) -> list:
    analysis = []
    for p in products:
        variants = p.get("variants", [])
        if not variants:
            continue
        variant = variants[0]
        try:
            price = float(variant.get("price") or 0)
        except (ValueError, TypeError):
            price = 0.0

        product_type = _detect_product_type(p.get("title", ""))
        base_cost = PRINTIFY_BASE_COSTS.get(product_type, DEFAULT_BASE_COST)
        margin = _calc_margin(price, base_cost)
        suggested = _suggested_price(base_cost)
        below_cost = price < base_cost
        low_margin = margin < 0.30
        overpriced = price > suggested * 1.5

        analysis.append({
            "id": p["id"],
            "title": p["title"],
            "status": p["status"],
            "product_type": product_type,
            "variant_id": variant["id"],
            "current_price": price,
            "base_cost": base_cost,
            "margin_pct": round(margin * 100, 1),
            "suggested_price": suggested,
            "flag": (
                "BELOW_COST" if below_cost
                else "LOW_MARGIN" if low_margin
                else "OVERPRICED" if overpriced
                else "OK"
            ),
        })

    analysis.sort(key=lambda x: x["margin_pct"])
    return analysis


def _fetch_competitor_prices() -> str:
    try:
        from ddgs import DDGS
        client = DDGS()
        lines = ["=== Competitor Pricing Intelligence (DuckDuckGo) ==="]
        for query in DDG_PRICING_QUERIES:
            results = client.text(query, max_results=2)
            for r in results or []:
                snippet = r.get("body", "").strip()
                if snippet:
                    lines.append(f"- {snippet[:350]}")
        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception as e:
        print(f"[pricing] DDG search failed: {e}")
        return ""


async def _gather_competitor_prices() -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_competitor_prices)


async def _synthesize_recommendations(
    product_analysis: list,
    competitor_data: str,
) -> tuple[str, str]:
    flagged = [p for p in product_analysis if p["flag"] != "OK"]
    all_lines = "\n".join(
        f"- {p['title']} ({p['status'].upper()}) | type:{p['product_type']} "
        f"| price:${p['current_price']:.2f} | margin:{p['margin_pct']}% "
        f"| suggested:${p['suggested_price']:.2f} | flag:{p['flag']}"
        for p in product_analysis
    ) or "- No products yet"

    prompt = f"""Analyze pricing for this print-on-demand store:

OUR PRODUCTS:
{all_lines}

PRICING CONTEXT:
- Printify base costs: T-Shirt ~$13.50, Hoodie ~$22.00, Long Sleeve ~$16.50
- Shopify fees: 2.9% + $0.30 per transaction
- Target margin: 45%+ after all fees
- Flagged: {len(flagged)} products need attention

COMPETITOR MARKET DATA:
{competitor_data or "No competitor data available — use industry knowledge."}

Generate a pricing report with:
1. Overall pricing health (1 sentence)
2. Products needing immediate attention (below cost or <30% margin)
3. Specific price recommendations with reasoning
4. Market positioning (are we competitive?)"""

    system = load_system_prompt("pricing", "pricing_agent", _PRICING_FALLBACK)
    try:
        text = await call_local(prompt, system=system)
        return text, "ollama"
    except Exception:
        text = await call_claude(prompt, system=system)
        return text, "claude"


def _load_previous_report() -> dict | None:
    path = os.path.join(PRICING_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _save_report(data: dict) -> str:
    os.makedirs(PRICING_DIR, exist_ok=True)

    latest_path = os.path.join(PRICING_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(PRICING_DIR, f"pricing_{ts}.md")

    products_md = "\n".join(
        f"- **{p['title']}** ({p['status'].upper()}) "
        f"| ${p['current_price']:.2f} → suggested ${p['suggested_price']:.2f} "
        f"| margin {p['margin_pct']}% | {p['flag']}"
        for p in (data.get("products") or [])
    ) or "- No products"

    md = f"""# Pricing Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

## Summary
- Total products analysed: {data.get('total_products', 0)}
- Products flagged: {data.get('flagged_count', 0)}
- Avg margin: {data.get('avg_margin_pct', 0):.1f}%

## Product Pricing
{products_md}

## Agent Recommendations
{data.get('recommendations', '')}
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
        products = await _fetch_shopify_products()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        msg = (
            "Shopify token expired — refresh it in rooms/captain/shopify-token.md"
            if status == 401
            else f"Shopify API error {status}"
        )
        return {"error": msg, "shopify_error": True}
    except Exception as e:
        return {"error": f"Shopify fetch failed: {e}", "shopify_error": True}

    product_analysis = _build_product_analysis(products)
    competitor_data = await _gather_competitor_prices()
    recommendations, model_used = await _synthesize_recommendations(product_analysis, competitor_data)

    flagged = [p for p in product_analysis if p["flag"] != "OK"]
    margins = [p["margin_pct"] for p in product_analysis]
    avg_margin = round(sum(margins) / len(margins), 1) if margins else 0.0

    data = {
        "total_products": len(product_analysis),
        "flagged_count": len(flagged),
        "avg_margin_pct": avg_margin,
        "products": product_analysis,
        "recommendations": recommendations,
        "model_used": model_used,
        "report_date": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "has_competitor_data": bool(competitor_data),
    }

    data["report_path"] = _save_report(data)
    return data


async def apply_pricing(product_ids: list[int] | None = None, dry_run: bool = True) -> dict:
    """
    Apply suggested prices to Shopify products.
    If product_ids is None, applies to all flagged products.
    Returns a summary of changes made (or would-be changes if dry_run=True).
    """
    report = await get_latest_report()
    if not report:
        return {"error": "No pricing report found. Run analysis first."}

    products = report.get("products", [])
    targets = [
        p for p in products
        if p["flag"] != "OK" and (product_ids is None or p["id"] in product_ids)
    ]

    results = []
    for p in targets:
        new_price = f"{p['suggested_price']:.2f}"
        if dry_run:
            results.append({
                "id": p["id"],
                "title": p["title"],
                "old_price": p["current_price"],
                "new_price": float(new_price),
                "applied": False,
                "dry_run": True,
            })
        else:
            ok = await _apply_shopify_price(p["id"], p["variant_id"], new_price)
            results.append({
                "id": p["id"],
                "title": p["title"],
                "old_price": p["current_price"],
                "new_price": float(new_price),
                "applied": ok,
                "dry_run": False,
            })

    return {
        "dry_run": dry_run,
        "changes": results,
        "applied_count": sum(1 for r in results if r.get("applied")),
        "total_targets": len(targets),
    }
