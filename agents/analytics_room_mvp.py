import os
import json
import glob
from datetime import datetime
from agents.llm_client import call_local, call_claude
from agents.brain import load_system_prompt
import httpx

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
ANALYTICS_DIR = os.path.join(BRAIN_PATH, "rooms", "analytics", "reports")
SHOPIFY_API_VERSION = "2025-01"

_ANALYSIS_FALLBACK = """You are the Analytics Agent for a print-on-demand Shopify store.
Analyze the provided store and pipeline data and generate a concise report.
Focus on:
- What's performing well (active products, revenue, niches)
- What's stalled or needs attention (drafts sitting idle, low approval rate)
- Pipeline health (research → design → approval → publish conversion)
- Specific, actionable recommendations for improvement
If previous report data is provided, call out key changes (up or down).
Be direct and specific. Use bullet points. 200 words max."""


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


async def _fetch_shopify_orders() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _shopify_url("orders.json?limit=250&status=any"),
            headers=_shopify_headers(),
        )
        r.raise_for_status()
        return r.json().get("orders", [])


def _load_pipeline_metrics() -> dict:
    briefs_dir = os.path.join(BRAIN_PATH, "rooms", "research", "briefs")
    approvals_dir = os.path.join(BRAIN_PATH, "rooms", "approval", "verdicts")

    briefs = glob.glob(os.path.join(briefs_dir, "brief_*.md"))
    verdicts = glob.glob(os.path.join(approvals_dir, "verdict_*.md"))

    approved = sum(1 for v in verdicts if "_approved_" in os.path.basename(v))
    rejected = len(verdicts) - approved
    approval_rate = round(approved / len(verdicts), 2) if verdicts else 0.0

    return {
        "briefs_run": len(briefs),
        "verdicts_collected": len(verdicts),
        "approved": approved,
        "rejected": rejected,
        "approval_rate": approval_rate,
    }


def _load_previous_report() -> dict | None:
    path = os.path.join(ANALYTICS_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _compute_delta(current: float | int, previous: float | int | None) -> str:
    if previous is None:
        return "—"
    diff = current - previous
    if diff == 0:
        return "—"
    if isinstance(diff, float):
        return f"+{diff:.2f}" if diff > 0 else f"{diff:.2f}"
    return f"+{diff}" if diff > 0 else str(diff)


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
                sales[pid] = {"units_sold": 0, "revenue": 0.0}
            sales[pid]["units_sold"] += item.get("quantity", 0)
            sales[pid]["revenue"] += float(item.get("price", 0)) * item.get("quantity", 0)

    result = []
    for p in products:
        pid = p["id"]
        stat = sales.get(pid, {"units_sold": 0, "revenue": 0.0})
        price = float(p["variants"][0]["price"]) if p.get("variants") else 29.99
        result.append({
            "id": pid,
            "title": p["title"],
            "status": p["status"],
            "price": price,
            "units_sold": stat["units_sold"],
            "revenue": round(stat["revenue"], 2),
            "created_at": p.get("created_at", "")[:10],
        })

    result.sort(key=lambda x: (-x["revenue"], -x["units_sold"]))
    return result


async def _synthesize_insights(
    products: list,
    orders: list,
    pipeline: dict,
    product_stats: list,
    previous: dict | None,
) -> tuple[str, str]:
    active_count = sum(1 for p in products if p["status"] == "active")
    draft_count = len(products) - active_count
    revenue = sum(
        float(o.get("total_price") or 0)
        for o in orders
        if o.get("financial_status") in ("paid", "partially_paid")
    )

    top_3 = product_stats[:3]
    top_str = "\n".join(
        f"  - {p['title']} ({p['status'].upper()}): {p['units_sold']} sold, ${p['revenue']:.2f} revenue"
        for p in top_3
    ) or "  - No products yet"

    prev_str = ""
    if previous:
        prev_str = f"""
Previous report ({previous.get('report_date', 'unknown')}):
  - Products: {previous.get('products_total', '?')} ({previous.get('products_active', '?')} active, {previous.get('products_draft', '?')} draft)
  - Orders: {previous.get('orders_total', '?')}
  - Revenue: ${previous.get('revenue_total', 0):.2f}
  - Pipeline: {previous.get('briefs_run', '?')} briefs, {previous.get('verdicts_collected', '?')} verdicts, {int((previous.get('approval_rate') or 0) * 100)}% approval rate
"""

    prompt = f"""Analyze this Shopify print-on-demand store:

CURRENT STORE DATA:
- Total products: {len(products)} ({active_count} active, {draft_count} draft)
- Total orders: {len(orders)}
- Revenue (paid orders): ${revenue:.2f}

TOP PRODUCTS:
{top_str}

PIPELINE METRICS:
- Briefs researched: {pipeline['briefs_run']}
- Verdicts collected: {pipeline['verdicts_collected']} ({pipeline['approved']} approved, {pipeline['rejected']} rejected)
- Approval rate: {int(pipeline['approval_rate'] * 100)}%
{prev_str}
Generate a concise analytics report with:
1. Key highlights (what's working)
2. Concerns (what needs attention)
3. Top 2-3 recommendations{"4. Changes since last report (call out key deltas)" if previous else ""}"""

    analysis_system = load_system_prompt("analytics", "analyst", _ANALYSIS_FALLBACK)
    try:
        text = await call_local(prompt, system=analysis_system)
        return text, "ollama"
    except Exception:
        text = await call_claude(prompt, system=analysis_system, room="analytics")
        return text, "claude"


def _save_report(data: dict) -> str:
    os.makedirs(ANALYTICS_DIR, exist_ok=True)

    latest_path = os.path.join(ANALYTICS_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(ANALYTICS_DIR, f"report_{ts}.md")

    prev_note = f"(compared to {data['previous_report_date']})" if data.get("previous_report_date") else "(first report)"

    def fmt_delta(key: str) -> str:
        d = (data.get("delta") or {}).get(key, "—")
        if d == "—":
            return ""
        positive = d.startswith("+")
        arrow = "↑" if positive else "↓"
        return f" [{d} {arrow}]"

    products_md = "\n".join(
        f"- {p['title']} ({p['status'].upper()}): {p['units_sold']} sold, ${p['revenue']:.2f}"
        for p in (data.get("top_products") or [])[:15]
    ) or "- No products yet"

    pipeline = data.get("pipeline", {})
    md = f"""# Analytics Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC {prev_note}

## Store Overview
- Total Products: {data['products_total']}{fmt_delta('products_total')} ({data['products_active']} active{fmt_delta('products_active')}, {data['products_draft']} draft)
- Total Orders: {data['orders_total']}{fmt_delta('orders_total')}
- Revenue (paid): ${data['revenue_total']:.2f}{fmt_delta('revenue_total')}

## Product Performance
{products_md}

## Pipeline Metrics
- Briefs run: {pipeline.get('briefs_run', 0)}{fmt_delta('briefs_run')}
- Verdicts collected: {pipeline.get('verdicts_collected', 0)} ({pipeline.get('approved', 0)} approved, {pipeline.get('rejected', 0)} rejected){fmt_delta('verdicts_collected')}
- Approval rate: {int((pipeline.get('approval_rate') or 0) * 100)}%{fmt_delta('approval_rate')}

## Agent Insights
{data.get('insights', '')}
"""

    with open(md_path, "w") as f:
        f.write(md)

    return md_path


async def get_latest_report() -> dict | None:
    path = os.path.join(ANALYTICS_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_analytics() -> dict:
    previous = _load_previous_report()

    try:
        products = await _fetch_shopify_products()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        msg = "Shopify token expired — refresh it in rooms/captain/shopify-token.md" if status == 401 else f"Shopify API error {status}"
        return {"error": msg, "shopify_error": True}
    except Exception as e:
        return {"error": f"Shopify products fetch failed: {e}", "shopify_error": True}

    try:
        orders = await _fetch_shopify_orders()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        msg = "Shopify token expired — refresh it in rooms/captain/shopify-token.md" if status == 401 else f"Shopify API error {status}"
        return {"error": msg, "shopify_error": True}
    except Exception as e:
        return {"error": f"Shopify orders fetch failed: {e}", "shopify_error": True}

    pipeline = _load_pipeline_metrics()
    product_stats = _build_product_stats(products, orders)

    active_count = sum(1 for p in products if p["status"] == "active")
    draft_count = len(products) - active_count
    revenue = round(sum(
        float(o.get("total_price") or 0)
        for o in orders
        if o.get("financial_status") in ("paid", "partially_paid")
    ), 2)

    delta: dict = {}
    if previous:
        delta["products_total"] = _compute_delta(len(products), previous.get("products_total"))
        delta["products_active"] = _compute_delta(active_count, previous.get("products_active"))
        delta["orders_total"] = _compute_delta(len(orders), previous.get("orders_total"))
        delta["revenue_total"] = _compute_delta(revenue, previous.get("revenue_total"))
        delta["briefs_run"] = _compute_delta(pipeline["briefs_run"], previous.get("briefs_run"))
        delta["verdicts_collected"] = _compute_delta(pipeline["verdicts_collected"], previous.get("verdicts_collected"))
        delta["approval_rate"] = _compute_delta(
            round(pipeline["approval_rate"] * 100),
            round((previous.get("approval_rate") or 0) * 100),
        )

    insights, model_used = await _synthesize_insights(products, orders, pipeline, product_stats, previous)

    data = {
        "products_total": len(products),
        "products_active": active_count,
        "products_draft": draft_count,
        "orders_total": len(orders),
        "revenue_total": revenue,
        "top_products": product_stats[:15],
        "pipeline": pipeline,
        "delta": delta,
        "insights": insights,
        "model_used": model_used,
        "report_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "previous_report_date": previous.get("report_date") if previous else None,
    }

    data["report_path"] = _save_report(data)
    return data
