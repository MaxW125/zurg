import os
import json
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=-6))
from agents.llm_client import call_claude_haiku
from agents.brain import load_system_prompt
import httpx

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
CS_DIR = os.path.join(BRAIN_PATH, "rooms", "cs", "reports")
SHOPIFY_API_VERSION = "2025-01"

_CS_FALLBACK = """You are the Customer Service Agent for a print-on-demand Shopify store.
Your job is to draft professional, warm, and concise customer messages.
Rules:
- Always address the customer by first name.
- Be empathetic but brief — 3-5 sentences max per message.
- For unfulfilled/delayed orders: apologise, give a realistic ETA, offer reassurance.
- For cancelled/refunded orders: confirm the action, give timeline for funds to appear.
- For review requests: be genuine, never pushy, mention the specific product they bought.
- Never promise anything you cannot guarantee (exact delivery dates, etc.).
- Sign off as "The Zurg Team" — never use a personal name.
- Output only the message body — no subject line, no JSON wrapper."""


def _shopify_headers() -> dict:
    return {
        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _shopify_url(path: str) -> str:
    store = os.getenv("SHOPIFY_STORE_URL", "")
    return f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/{path}"


async def _fetch_orders() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _shopify_url("orders.json?limit=250&status=any"),
            headers=_shopify_headers(),
        )
        r.raise_for_status()
        return r.json().get("orders", [])


def _customer_first_name(order: dict) -> str:
    name = (order.get("customer") or {}).get("first_name", "")
    return name or "there"


def _product_names(order: dict) -> list[str]:
    return [item.get("title", "your item") for item in order.get("line_items", [])]


def _categorise_orders(orders: list) -> tuple[list, list]:
    now = datetime.now(timezone.utc)
    attention = []
    review_queue = []

    for order in orders:
        created_raw = order.get("created_at", "")
        financial = order.get("financial_status", "")
        fulfillment = order.get("fulfillment_status") or "unfulfilled"
        cancelled_at = order.get("cancelled_at")

        try:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except Exception:
            continue

        age_days = (now - created_dt).days
        customer = order.get("customer") or {}
        email = customer.get("email", "")
        first_name = _customer_first_name(order)
        products = _product_names(order)
        order_number = order.get("name", f"#{order.get('id', '')}")
        total = order.get("total_price", "0.00")

        base = {
            "order_id": order.get("id"),
            "order_number": order_number,
            "customer_name": first_name,
            "customer_email": email,
            "product_names": products,
            "order_date": created_raw[:10],
            "total": total,
        }

        if cancelled_at:
            attention.append({**base, "issue": "cancelled", "issue_label": "CANCELLED", "drafted_reply": ""})
            continue

        if financial in ("refunded", "partially_refunded"):
            attention.append({**base, "issue": financial, "issue_label": financial.upper().replace("_", " "), "drafted_reply": ""})
            continue

        if fulfillment == "unfulfilled" and age_days >= 3:
            label = f"UNFULFILLED {age_days}D"
            attention.append({**base, "issue": "unfulfilled", "issue_label": label, "drafted_reply": ""})
            continue

        # Fulfilled orders older than 7 days and no more than 60 days old — review queue
        if fulfillment == "fulfilled" and 7 <= age_days <= 60 and email:
            fulfilled_events = order.get("fulfillments", [])
            fulfilled_date = fulfilled_events[0].get("created_at", "")[:10] if fulfilled_events else created_raw[:10]
            review_queue.append({
                "order_id": order.get("id"),
                "order_number": order_number,
                "customer_name": first_name,
                "customer_email": email,
                "product_names": products,
                "fulfilled_date": fulfilled_date,
                "review_message": "",
            })

    attention.sort(key=lambda x: x["order_date"])
    return attention, review_queue


async def _draft_messages(attention: list, review_queue: list, system: str) -> tuple[list, list, str]:
    if not attention and not review_queue:
        return attention, review_queue, "none"

    lines = []

    if attention:
        lines.append("=== ORDERS NEEDING ATTENTION ===")
        for i, o in enumerate(attention):
            lines.append(
                f"[{i}] Customer: {o['customer_name']} | Order: {o['order_number']} | "
                f"Issue: {o['issue_label']} | Products: {', '.join(o['product_names'])} | "
                f"Order date: {o['order_date']} | Total: ${o['total']}"
            )

    if review_queue:
        lines.append("\n=== REVIEW REQUEST QUEUE ===")
        for j, r in enumerate(review_queue):
            lines.append(
                f"[R{j}] Customer: {r['customer_name']} | Order: {r['order_number']} | "
                f"Products: {', '.join(r['product_names'])} | Fulfilled: {r['fulfilled_date']}"
            )

    prompt = f"""{chr(10).join(lines)}

Draft a short, warm customer service message for each entry above.
Format your response EXACTLY like this (one block per order, nothing else):

[0]
<drafted message here>

[1]
<drafted message here>

[R0]
<review request message here>

[R1]
<review request message here>"""

    try:
        raw = await call_claude_haiku(prompt, system=system, room="cs")
        model_used = "haiku"
    except Exception:
        raw = await call_claude_haiku(prompt, system=system, room="cs")
        model_used = "claude"

    # Parse responses back into the lists
    import re
    blocks = re.split(r'\n(?=\[(?:R?\d+)\])', raw.strip())
    for block in blocks:
        m = re.match(r'^\[R(\d+)\]\s*(.*)', block, re.DOTALL)
        if m:
            idx = int(m.group(1))
            if idx < len(review_queue):
                review_queue[idx]["review_message"] = m.group(2).strip()
            continue
        m = re.match(r'^\[(\d+)\]\s*(.*)', block, re.DOTALL)
        if m:
            idx = int(m.group(1))
            if idx < len(attention):
                attention[idx]["drafted_reply"] = m.group(2).strip()

    return attention, review_queue, model_used


def _save_report(data: dict) -> str:
    os.makedirs(CS_DIR, exist_ok=True)

    latest_path = os.path.join(CS_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(CS_DIR, f"cs_{ts}.md")

    attention_md = "\n".join(
        f"- {o['order_number']} | {o['customer_name']} | {o['issue_label']}"
        for o in data.get("attention_orders", [])
    ) or "- None"

    review_md = "\n".join(
        f"- {r['order_number']} | {r['customer_name']} | fulfilled {r['fulfilled_date']}"
        for r in data.get("review_queue", [])
    ) or "- None"

    md = f"""# CS Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

## Orders Needing Attention
{attention_md}

## Review Request Queue
{review_md}

---
Orders scanned: {data.get('orders_scanned', 0)}
Model: {data.get('model_used', '—')}
"""
    with open(md_path, "w") as f:
        f.write(md)

    return md_path


async def get_latest_report() -> dict | None:
    path = os.path.join(CS_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_cs() -> dict:
    try:
        orders = await _fetch_orders()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        msg = "Shopify token expired — refresh it in rooms/captain/shopify-token.md" if status == 401 else f"Shopify API error {status}"
        return {"error": msg, "shopify_error": True}
    except Exception as e:
        return {"error": f"Shopify orders fetch failed: {e}", "shopify_error": True}

    attention, review_queue = _categorise_orders(orders)

    system = load_system_prompt("cs", "cs", _CS_FALLBACK)
    attention, review_queue, model_used = await _draft_messages(attention, review_queue, system)

    data = {
        "run_date": datetime.now(_CST).strftime("%Y-%m-%d"),
        "orders_scanned": len(orders),
        "attention_orders": attention,
        "review_queue": review_queue,
        "model_used": model_used,
    }

    data["report_path"] = _save_report(data)
    return data
