import asyncio
import os
from datetime import datetime, timezone, timedelta

import httpx
import agents.etsy_client as etsy

SHOPIFY_API_VERSION = "2025-01"
_WINDOW_DAYS = 30


def _shopify_headers() -> dict:
    return {
        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _shopify_url(path: str) -> str:
    store = os.getenv("SHOPIFY_STORE_URL", "")
    return f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/{path}"


async def _shopify_snapshot() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        count_r, orders_r = await asyncio.gather(
            client.get(
                _shopify_url("products/count.json?status=active"),
                headers=_shopify_headers(),
            ),
            client.get(
                _shopify_url(
                    f"orders.json?status=any&financial_status=paid"
                    f"&created_at_min={cutoff}&limit=250"
                ),
                headers=_shopify_headers(),
            ),
            return_exceptions=True,
        )

    product_count = 0
    if not isinstance(count_r, Exception):
        count_r.raise_for_status()
        product_count = count_r.json().get("count", 0)

    order_count = 0
    revenue_30d = 0.0
    if not isinstance(orders_r, Exception):
        orders_r.raise_for_status()
        orders = orders_r.json().get("orders", [])
        order_count = len(orders)
        revenue_30d = round(sum(float(o.get("total_price") or 0) for o in orders), 2)

    return {
        "product_count": product_count,
        "order_count": order_count,
        "revenue_30d": revenue_30d,
    }


async def _etsy_snapshot() -> dict:
    if not etsy.is_configured():
        return {"listing_count": 0, "receipt_count": 0, "revenue_30d": 0.0, "configured": False}

    listings, receipts = await asyncio.gather(
        etsy.fetch_listings(state="active", limit=100),
        etsy.fetch_receipts(limit=100),
        return_exceptions=True,
    )

    listing_count = len(listings) if not isinstance(listings, Exception) else 0

    receipt_count = 0
    revenue_30d = 0.0
    if not isinstance(receipts, Exception):
        cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)).timestamp()
        for r in receipts:
            if not r.get("was_paid"):
                continue
            ts = r.get("create_timestamp") or r.get("created_timestamp") or 0
            if ts >= cutoff_ts:
                receipt_count += 1
                grandtotal = r.get("grandtotal", {})
                if isinstance(grandtotal, dict):
                    divisor = grandtotal.get("divisor") or 100
                    revenue_30d += grandtotal.get("amount", 0) / divisor
                else:
                    revenue_30d += float(grandtotal or 0)

    return {
        "listing_count": listing_count,
        "receipt_count": receipt_count,
        "revenue_30d": round(revenue_30d, 2),
        "configured": True,
    }


async def fetch_store_snapshot() -> dict:
    """Pull live counts and revenue totals from Shopify and Etsy. Designed to complete in <5s."""
    shopify_data, etsy_data = await asyncio.gather(
        _shopify_snapshot(),
        _etsy_snapshot(),
        return_exceptions=True,
    )

    if isinstance(shopify_data, Exception):
        shopify_data = {
            "product_count": 0,
            "order_count": 0,
            "revenue_30d": 0.0,
            "error": str(shopify_data),
        }
    if isinstance(etsy_data, Exception):
        etsy_data = {
            "listing_count": 0,
            "receipt_count": 0,
            "revenue_30d": 0.0,
            "configured": False,
            "error": str(etsy_data),
        }

    return {
        "shopify": shopify_data,
        "etsy": etsy_data,
        "window_days": _WINDOW_DAYS,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def format_snapshot_for_prompt(snapshot: dict) -> str:
    """Compact briefing block injected at the top of the CEO prompt for store questions."""
    shopify = snapshot.get("shopify", {})
    etsy_data = snapshot.get("etsy", {})
    window = snapshot.get("window_days", 30)

    lines = [
        "=== LIVE STORE DATA (just fetched) ===",
        f"Shopify: {shopify.get('product_count', 0)} active products | "
        f"{shopify.get('order_count', 0)} paid orders (last {window} days) | "
        f"${shopify.get('revenue_30d', 0.0):.2f} revenue (last {window} days)",
    ]

    if etsy_data.get("configured"):
        lines.append(
            f"Etsy: {etsy_data.get('listing_count', 0)} active listings | "
            f"{etsy_data.get('receipt_count', 0)} paid receipts (last {window} days) | "
            f"${etsy_data.get('revenue_30d', 0.0):.2f} revenue (last {window} days)"
        )
    else:
        lines.append("Etsy: not connected (OAuth not configured)")

    if shopify.get("error"):
        lines.append(f"[Shopify error: {shopify['error']}]")
    if etsy_data.get("error"):
        lines.append(f"[Etsy error: {etsy_data['error']}]")

    lines.append("======================================")
    return "\n".join(lines)
