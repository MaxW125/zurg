import os
import json
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=-6))
from agents.llm_client import call_claude_haiku
from agents.brain import load_system_prompt

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
WAR_ROOM_DIR = os.path.join(BRAIN_PATH, "rooms", "war_room", "reports")

_WAR_ROOM_FALLBACK = """You are the War Room Strategist for a print-on-demand Shopify business run by an AI CEO named Zurg.
Your job is to synthesise status reports from all active rooms — Analytics, Pricing, Shop Health, and CS — into one prioritised action plan.
Rules:
- Be specific. Reference exact product names, dollar amounts, or issue counts from the reports.
- Prioritise ruthlessly: the owner has 30 minutes a day. Tell them what matters most first.
- Fix = something broken or losing money right now. Launch = growth opportunity to pursue this week. Watch = no action needed but monitor.
- Each item must be one sentence, max 20 words.
- Output EXACTLY this JSON structure, nothing else:
{
  "summary": "<2–3 sentence executive summary of the business state>",
  "fix": ["<item>", ...],
  "launch": ["<item>", ...],
  "watch": ["<item>", ...]
}"""


def _load_room_report(room: str) -> dict | None:
    path = os.path.join(BRAIN_PATH, "rooms", room, "reports", "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _summarise_analytics(r: dict) -> str:
    lines = [
        f"ANALYTICS — {r.get('report_date', 'unknown date')}",
        f"  Products: {r.get('products_active', 0)} active / {r.get('products_total', 0)} total",
        f"  Orders: {r.get('orders_total', 0)} | Revenue: ${r.get('revenue_total', '0')}",
    ]
    top = r.get("top_products", [])
    if top:
        lines.append(f"  Top product: {top[0].get('title', '?')} ({top[0].get('orders', 0)} orders)")
    insights = r.get("insights", "")
    if insights:
        lines.append(f"  Insights: {str(insights)[:300]}")
    return "\n".join(lines)


def _summarise_pricing(r: dict) -> str:
    lines = [
        f"PRICING — {r.get('run_date', 'unknown date')}",
        f"  Products analysed: {r.get('products_analysed', 0)}",
    ]
    stats = r.get("product_stats", [])
    for s in stats[:5]:
        rec = s.get("recommendation", "KEEP")
        lines.append(f"  {s.get('title', '?')} — {rec} (current: ${s.get('current_price', '?')})")
    analysis = r.get("analysis", "")
    if analysis:
        lines.append(f"  Analysis: {str(analysis)[:300]}")
    return "\n".join(lines)


def _summarise_shop_health(r: dict) -> str:
    products = r.get("products", [])
    critical = [p for p in products if p.get("severity") == "critical"]
    warning = [p for p in products if p.get("severity") == "warning"]
    lines = [
        f"SHOP HEALTH — {r.get('run_date', 'unknown date')}",
        f"  Scanned: {r.get('products_scanned', 0)} | Flagged: {r.get('flagged_count', 0)}",
        f"  Critical: {len(critical)} | Warnings: {len(warning)}",
    ]
    for p in critical[:3]:
        lines.append(f"  CRITICAL — {p.get('title', '?')}: {', '.join(p.get('issues', []))}")
    for p in warning[:3]:
        lines.append(f"  WARNING — {p.get('title', '?')}: {', '.join(p.get('issues', []))}")
    return "\n".join(lines)


def _summarise_cs(r: dict) -> str:
    attention = r.get("attention_orders", [])
    review_q = r.get("review_queue", [])
    lines = [
        f"CS — {r.get('run_date', 'unknown date')}",
        f"  Orders scanned: {r.get('orders_scanned', 0)}",
        f"  Needs attention: {len(attention)} | Review requests ready: {len(review_q)}",
    ]
    for o in attention[:3]:
        lines.append(f"  ATTENTION — Order {o.get('order_number', '?')}: {o.get('issue_label', '?')}")
    return "\n".join(lines)


def _build_briefing(reports: dict) -> str:
    sections = []
    if reports.get("analytics"):
        sections.append(_summarise_analytics(reports["analytics"]))
    else:
        sections.append("ANALYTICS — no report available")
    if reports.get("pricing"):
        sections.append(_summarise_pricing(reports["pricing"]))
    else:
        sections.append("PRICING — no report available")
    if reports.get("shop_health"):
        sections.append(_summarise_shop_health(reports["shop_health"]))
    else:
        sections.append("SHOP HEALTH — no report available")
    if reports.get("cs"):
        sections.append(_summarise_cs(reports["cs"]))
    else:
        sections.append("CS — no report available")
    return "\n\n".join(sections)


def _save_report(data: dict) -> str:
    os.makedirs(WAR_ROOM_DIR, exist_ok=True)

    latest_path = os.path.join(WAR_ROOM_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(WAR_ROOM_DIR, f"war_room_{ts}.md")

    fix_md = "\n".join(f"- {i}" for i in data.get("fix", [])) or "- None"
    launch_md = "\n".join(f"- {i}" for i in data.get("launch", [])) or "- None"
    watch_md = "\n".join(f"- {i}" for i in data.get("watch", [])) or "- None"

    md = f"""# War Room Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

## Summary
{data.get('summary', '')}

## Fix (Urgent)
{fix_md}

## Launch (Growth)
{launch_md}

## Watch (Monitor)
{watch_md}

---
Model: {data.get('model_used', '—')}
"""
    with open(md_path, "w") as f:
        f.write(md)

    return md_path


async def get_latest_report() -> dict | None:
    path = os.path.join(WAR_ROOM_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_war_room() -> dict:
    reports = {
        "analytics": _load_room_report("analytics"),
        "pricing": _load_room_report("pricing"),
        "shop_health": _load_room_report("shop_health"),
        "cs": _load_room_report("cs"),
    }

    briefing = _build_briefing(reports)
    system = load_system_prompt("war_room", "strategist", _WAR_ROOM_FALLBACK)

    prompt = f"""Here is the current status across all active rooms:

{briefing}

Synthesise this into a prioritised action plan. Output only the JSON specified."""

    try:
        raw = await call_claude_haiku(prompt, system=system, room="war_room")
        model_used = "haiku"
    except Exception:
        raw = await call_claude_haiku(prompt, system=system, room="warroom")
        model_used = "claude"

    # Extract JSON from response
    import re
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        try:
            plan = json.loads(m.group(0))
        except Exception:
            plan = {"summary": raw.strip(), "fix": [], "launch": [], "watch": []}
    else:
        plan = {"summary": raw.strip(), "fix": [], "launch": [], "watch": []}

    def _flatten(items: list) -> list[str]:
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                result.append(" — ".join(str(v) for v in item.values() if v))
        return result

    data = {
        "run_date": datetime.now(_CST).strftime("%Y-%m-%d %H:%M"),
        "model_used": model_used,
        "summary": plan.get("summary", ""),
        "fix": _flatten(plan.get("fix", [])),
        "launch": _flatten(plan.get("launch", [])),
        "watch": _flatten(plan.get("watch", [])),
        "rooms_included": [k for k, v in reports.items() if v is not None],
    }

    data["report_path"] = _save_report(data)
    return data
