import os
import json
import asyncio
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=-6))
from agents.llm_client import call_claude_haiku
from agents.brain import load_system_prompt
import httpx

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
SHOP_HEALTH_DIR = os.path.join(BRAIN_PATH, "rooms", "shop_health", "reports")
SHOPIFY_API_VERSION = "2025-01"

ETSY_BASE      = "https://openapi.etsy.com/v3"
ETSY_SHOP_ID   = os.getenv("ETSY_SHOP_ID", "")
ETSY_API_KEY   = os.getenv("ETSY_API_KEY", "")
ETSY_SECRET    = os.getenv("ETSY_SHARED_SECRET", "")


def _etsy_headers() -> dict | None:
    if not ETSY_API_KEY or not ETSY_SECRET:
        return None
    return {"x-api-key": f"{ETSY_API_KEY}:{ETSY_SECRET}"}

_SHOP_HEALTH_FALLBACK = """You are the Shop Health Agent for a print-on-demand Shopify store.
Your job is to audit active product listings for SEO weaknesses and staleness, then give precise, actionable fixes.
Rules:
- Be specific: if a title is too short, suggest a better one. If tags are missing, suggest exact tags to add.
- For stale listings with no sales, recommend a concrete action: lower price, refresh title, run a discount.
- For thin descriptions, draft a short 2-3 sentence replacement that includes keywords, use case, and a call to action.
- Keep each recommendation under 40 words.
- Never recommend deleting a listing — always recommend a fix.
- Format: one recommendation per product, labelled [P0], [P1], etc. Nothing else."""


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


async def _fetch_etsy_listings() -> list:
    headers = _etsy_headers()
    if not headers or not ETSY_SHOP_ID:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/active",
                headers=headers,
                params={"limit": 100, "includes": ""},
            )
            r.raise_for_status()
            return r.json().get("results", [])
    except Exception as e:
        print(f"[shop_health] Etsy listings fetch failed: {e}")
        return []


def _audit_etsy_listing(listing: dict) -> dict:
    title       = listing.get("title") or ""
    tags        = listing.get("tags") or []
    views       = listing.get("views", 0)
    favorites   = listing.get("num_favorers", 0)
    description = listing.get("description") or ""
    listing_id  = listing.get("listing_id")
    url         = listing.get("url") or f"https://www.etsy.com/listing/{listing_id}"

    created_ts = listing.get("creation_timestamp") or listing.get("create_date", 0)
    now_ts     = datetime.now(timezone.utc).timestamp()
    days_live  = int((now_ts - created_ts) / 86400) if created_ts else 0

    issues = []

    if len(title) < 20:
        issues.append("TITLE TOO SHORT")
    elif len(title) > 140:
        issues.append("TITLE TOO LONG")

    # Etsy allows 13 tags — fewer than 8 is leaving SEO on the table
    if len(tags) < 8:
        issues.append(f"NEEDS MORE TAGS ({len(tags)}/13)")

    if len(description) < 50:
        issues.append("THIN DESCRIPTION")

    if days_live >= 14 and views == 0:
        issues.append("ZERO VIEWS")

    severity = "ok"
    if "ZERO VIEWS" in issues:
        severity = "critical"
    elif issues:
        severity = "warning"

    return {
        "listing_id": listing_id,
        "title":      title,
        "url":        url,
        "tag_count":  len(tags),
        "tags":       tags,
        "views":      views,
        "favorites":  favorites,
        "days_live":  days_live,
        "issues":     issues,
        "severity":   severity,
        "recommendation": "",
    }


async def _get_etsy_recommendations(audits: list, system: str) -> tuple[list, str]:
    flagged = [a for a in audits if a["issues"]]
    if not flagged:
        return audits, "none"

    lines = []
    for i, a in enumerate(flagged):
        lines.append(
            f"[E{i}] \"{a['title']}\" | Issues: {', '.join(a['issues'])} | "
            f"Tags: {a['tag_count']}/13 | Views: {a['views']} | "
            f"Favorites: {a['favorites']} | Days live: {a['days_live']}"
        )

    prompt = f"""These are Etsy listings that need SEO fixes:

{chr(10).join(lines)}

Give one actionable fix recommendation per listing above.
Format EXACTLY as:

[E0]
<recommendation here>

[E1]
<recommendation here>"""

    try:
        raw = await call_claude_haiku(prompt, system=system, room="shop_health")
        model_used = "haiku"
    except Exception:
        raw = await call_claude_haiku(prompt, system=system, room="shophealth")
        model_used = "claude"

    import re
    blocks = re.split(r'\n(?=\[E\d+\])', raw.strip())
    recs = {}
    for block in blocks:
        m = re.match(r'^\[E(\d+)\]\s*(.*)', block, re.DOTALL)
        if m:
            recs[int(m.group(1))] = m.group(2).strip()

    fi = 0
    for a in audits:
        if a["issues"]:
            a["recommendation"] = recs.get(fi, "")
            fi += 1

    return audits, model_used


def _last_sale_date(product_id: int, orders: list) -> datetime | None:
    """Return the most recent order date that included this product."""
    last = None
    for order in orders:
        for item in order.get("line_items", []):
            if item.get("product_id") == product_id:
                raw = order.get("created_at", "")
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if last is None or dt > last:
                        last = dt
                except Exception:
                    pass
    return last


def _total_sales(product_id: int, orders: list) -> int:
    count = 0
    for order in orders:
        for item in order.get("line_items", []):
            if item.get("product_id") == product_id:
                count += item.get("quantity", 1)
    return count


def _audit_product(product: dict, orders: list) -> dict:
    now = datetime.now(timezone.utc)
    product_id = product.get("id")
    title = product.get("title", "")
    tags_raw = product.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
    description = product.get("body_html", "") or ""
    # Strip basic HTML tags for length check
    import re
    desc_text = re.sub(r"<[^>]+>", "", description).strip()

    created_raw = product.get("created_at", "")
    try:
        created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        days_live = (now - created_dt).days
    except Exception:
        days_live = 0

    sales = _total_sales(product_id, orders)
    last_sale = _last_sale_date(product_id, orders)
    days_since_sale = (now - last_sale).days if last_sale else None

    issues = []

    if len(title) < 20:
        issues.append("TITLE TOO SHORT")
    elif len(title) > 100:
        issues.append("TITLE TOO LONG")

    if len(tags) < 3:
        issues.append("NEEDS MORE TAGS")

    if len(desc_text) < 50:
        issues.append("THIN DESCRIPTION")

    if days_live >= 30 and sales == 0:
        issues.append("NO SALES 30+ DAYS")

    if days_since_sale is not None and days_since_sale >= 45 and days_live >= 30:
        issues.append("STALE LISTING")

    severity = "ok"
    if any(i in issues for i in ("NO SALES 30+ DAYS", "STALE LISTING")):
        severity = "critical"
    elif issues:
        severity = "warning"

    return {
        "product_id": product_id,
        "title": title,
        "tag_count": len(tags),
        "tags": tags,
        "desc_length": len(desc_text),
        "days_live": days_live,
        "total_sales": sales,
        "days_since_sale": days_since_sale,
        "issues": issues,
        "severity": severity,
        "recommendation": "",
    }


async def _get_recommendations(audits: list, system: str) -> tuple[list, str]:
    flagged = [a for a in audits if a["issues"]]
    if not flagged:
        return audits, "none"

    lines = []
    for i, a in enumerate(flagged):
        lines.append(
            f"[P{i}] \"{a['title']}\" | Issues: {', '.join(a['issues'])} | "
            f"Tags: {a['tag_count']} | Desc chars: {a['desc_length']} | "
            f"Days live: {a['days_live']} | Total sales: {a['total_sales']} | "
            f"Days since last sale: {a['days_since_sale'] if a['days_since_sale'] is not None else 'never sold'}"
        )

    prompt = f"""{chr(10).join(lines)}

Give one actionable fix recommendation per listing above.
Format EXACTLY as:

[P0]
<recommendation here>

[P1]
<recommendation here>"""

    try:
        raw = await call_claude_haiku(prompt, system=system, room="shop_health")
        model_used = "haiku"
    except Exception:
        raw = await call_claude_haiku(prompt, system=system, room="shophealth")
        model_used = "claude"

    import re
    blocks = re.split(r'\n(?=\[P\d+\])', raw.strip())
    recs = {}
    for block in blocks:
        m = re.match(r'^\[P(\d+)\]\s*(.*)', block, re.DOTALL)
        if m:
            recs[int(m.group(1))] = m.group(2).strip()

    fi = 0
    for a in audits:
        if a["issues"]:
            a["recommendation"] = recs.get(fi, "")
            fi += 1

    return audits, model_used


def _save_report(data: dict) -> str:
    os.makedirs(SHOP_HEALTH_DIR, exist_ok=True)

    latest_path = os.path.join(SHOP_HEALTH_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(SHOP_HEALTH_DIR, f"shop_health_{ts}.md")

    critical = [a for a in data.get("products", []) if a["severity"] == "critical"]
    warning = [a for a in data.get("products", []) if a["severity"] == "warning"]
    ok = [a for a in data.get("products", []) if a["severity"] == "ok"]

    def _product_line(a):
        issues = ", ".join(a["issues"]) if a["issues"] else "—"
        return f"- **{a['title']}** | Issues: {issues} | Sales: {a['total_sales']} | Days live: {a['days_live']}"

    critical_md = "\n".join(_product_line(a) for a in critical) or "- None"
    warning_md = "\n".join(_product_line(a) for a in warning) or "- None"
    ok_md = "\n".join(_product_line(a) for a in ok) or "- None"

    md = f"""# Shop Health Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

## Critical
{critical_md}

## Warnings
{warning_md}

## Healthy
{ok_md}

---
Products scanned: {data.get('products_scanned', 0)}
Flagged: {data.get('flagged_count', 0)}
Model: {data.get('model_used', '—')}
"""
    with open(md_path, "w") as f:
        f.write(md)

    return md_path


async def get_latest_report() -> dict | None:
    path = os.path.join(SHOP_HEALTH_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_shop_health() -> dict:
    # Fetch Shopify products + orders and Etsy listings in parallel
    try:
        (products, orders), etsy_listings = await asyncio.gather(
            _fetch_shopify(),
            _fetch_etsy_listings(),
        )
    except Exception as e:
        return {"error": f"Shopify fetch failed: {e}", "shopify_error": True}

    system = load_system_prompt("shop_health", "shop_health", _SHOP_HEALTH_FALLBACK)

    # Audit both channels
    shopify_audits = [_audit_product(p, orders) for p in products]
    etsy_audits    = [_audit_etsy_listing(l) for l in etsy_listings]

    shopify_audits, shopify_model = await _get_recommendations(shopify_audits, system)
    etsy_audits, etsy_model = await _get_etsy_recommendations(etsy_audits, system)

    model_used = shopify_model if shopify_model != "none" else etsy_model

    flagged_shopify = [a for a in shopify_audits if a["issues"]]
    flagged_etsy    = [a for a in etsy_audits if a["issues"]]

    data = {
        "run_date":           datetime.now(_CST).strftime("%Y-%m-%d"),
        "products_scanned":   len(products),
        "flagged_count":      len(flagged_shopify),
        "etsy_scanned":       len(etsy_listings),
        "etsy_flagged":       len(flagged_etsy),
        "model_used":         model_used,
        "products":           shopify_audits,
        "etsy_listings":      etsy_audits,
    }

    data["report_path"] = _save_report(data)
    return data


async def _fetch_shopify() -> tuple[list, list]:
    try:
        products = await _fetch_products()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        msg = "Shopify token expired — refresh it in rooms/captain/shopify-token.md" if status == 401 else f"Shopify API error {status}"
        raise RuntimeError(msg)

    try:
        orders = await _fetch_orders()
    except Exception:
        orders = []

    return products, orders
