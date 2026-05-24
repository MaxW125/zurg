import os
import json
import re
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=-6))
from agents.llm_client import call_claude_haiku
from agents.brain import load_system_prompt

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
WAR_ROOM_DIR = os.path.join(BRAIN_PATH, "rooms", "war_room", "reports")

_WAR_ROOM_FALLBACK = """You are the War Room Strategist for a print-on-demand Shopify + Etsy business run by an AI CEO named Zurg.
Your job is to synthesise overnight status reports from all 14 active rooms into one prioritised action plan.
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


# ── Per-room highlight functions (rule-based, no LLM) ─────────────────────────

def _hl_research(r: dict) -> str:
    cycles = r.get("cycles_run", 0)
    briefs = r.get("briefs", [])
    if r.get("nothing_to_report") or cycles == 0:
        return "No research cycles ran today."
    niches = ", ".join(b.get("niche", "?") for b in briefs[:3])
    more = f" +{len(briefs) - 3} more" if len(briefs) > 3 else ""
    return f"{cycles} niche{'s' if cycles != 1 else ''} researched: {niches}{more}."


def _hl_design(r: dict) -> str:
    n = r.get("designs_generated", 0)
    if r.get("nothing_to_report") or n == 0:
        return "No designs generated today."
    designs = r.get("designs", [])
    types = ", ".join(d.get("product_type", "?") for d in designs[:3])
    return f"{n} design{'s' if n != 1 else ''} generated ({types})."


def _hl_approval(r: dict) -> str:
    approved = r.get("approved_today", 0)
    rejected = r.get("rejected_today", 0)
    total = approved + rejected
    if total == 0:
        return "No approval decisions today."
    return f"{approved} approved, {rejected} rejected ({total} reviewed)."


def _hl_factory(r: dict) -> str:
    n = r.get("products_published", 0)
    if r.get("nothing_to_report") or n == 0:
        return "No products published today."
    publishes = r.get("publishes", [])
    etsy = r.get("etsy_count", 0)
    titles = ", ".join(p.get("title", "?")[:30] for p in publishes[:2])
    more = f" +{len(publishes) - 2} more" if len(publishes) > 2 else ""
    return f"{n} product{'s' if n != 1 else ''} published to Shopify + {etsy} to Etsy: {titles}{more}."


def _hl_analytics(r: dict) -> str:
    products = r.get("products_active", r.get("products_total", 0))
    orders = r.get("orders_total", 0)
    revenue = r.get("revenue_total", "0")
    return f"{products} active products, {orders} orders, ${revenue} revenue."


def _hl_pricing(r: dict) -> str:
    analysed = r.get("products_analysed", 0)
    stats = r.get("product_stats", [])
    repricing = [s for s in stats if s.get("recommendation", "KEEP") != "KEEP"]
    if analysed == 0:
        return "No pricing data available."
    return f"{analysed} products analyzed, {len(repricing)} repricing recommendation{'s' if len(repricing) != 1 else ''}."


def _hl_shop_health(r: dict) -> str:
    scanned = r.get("products_scanned", 0)
    flagged = r.get("flagged_count", 0)
    products = r.get("products", [])
    critical = sum(1 for p in products if p.get("severity") == "critical")
    if scanned == 0:
        return "No shop health data available."
    if flagged == 0:
        return f"{scanned} products scanned, all healthy."
    return f"{scanned} scanned, {flagged} flagged ({critical} critical)."


def _hl_cs(r: dict) -> str:
    scanned = r.get("orders_scanned", 0)
    attention = len(r.get("attention_orders", []))
    reviews = len(r.get("review_queue", []))
    if scanned == 0:
        return "No CS data available."
    if attention == 0 and reviews == 0:
        return f"{scanned} orders scanned, nothing needs attention."
    return f"{attention} order{'s' if attention != 1 else ''} need attention, {reviews} review request{'s' if reviews != 1 else ''} ready."


def _hl_monitoring(r: dict) -> str:
    overall = r.get("overall_status", "unknown")
    alerts = r.get("alerts", [])
    if overall == "green" and not alerts:
        return "All systems healthy — no alerts."
    if alerts:
        return f"Status: {overall.upper()}. {len(alerts)} alert(s): {str(alerts[0])[:80]}."
    return f"Status: {overall.upper()}."


def _hl_media_bay(r: dict) -> str:
    n = r.get("content_generated_today", 0)
    if n == 0:
        return "No content generated today."
    products = r.get("products_covered", [])
    titles = ", ".join(p[:30] for p in products[:2])
    more = f" +{len(products) - 2} more" if len(products) > 2 else ""
    return f"{n} content piece{'s' if n != 1 else ''} generated for: {titles}{more}."


def _hl_armory(r: dict) -> str:
    total = r.get("total_skills", 0)
    new_today = r.get("new_today", 0)
    if new_today == 0:
        return f"No new skills today ({total} total in armory)."
    skills = r.get("skills_today", [])
    names = ", ".join(s.get("name", "?") for s in skills[:2])
    return f"{new_today} new skill{'s' if new_today != 1 else ''} added: {names}. {total} total."


def _hl_radar_bay(r: dict) -> str:
    proposals = r.get("proposals", [])
    n = len(proposals)
    if n == 0:
        return "No improvement proposals generated."
    top = proposals[0] if proposals else {}
    return f"{n} proposal{'s' if n != 1 else ''} generated. Top: {top.get('title', '?')[:60]}."


def _hl_memory(r: dict) -> str:
    total_md = r.get("total_md_files", 0)
    total_kb = r.get("total_kb", 0)
    briefs = r.get("briefs_count", 0)
    verdicts = r.get("verdicts_count", 0)
    if total_md == 0:
        return "Memory room data unavailable."
    return f"Vault: {total_md} files ({total_kb} KB). {briefs} briefs, {verdicts} verdicts accumulated."


def _hl_treasury(r: dict) -> str:
    spend = r.get("spend_today", 0)
    cap = r.get("daily_cap_usd", 1.0)
    pct = r.get("cap_pct", 0)
    images = r.get("images_generated_today", 0)
    cap_str = f" ({pct}% of ${cap:.2f} cap)" if cap > 0 else ""
    return f"${spend:.4f} spent today{cap_str}. {images} image{'s' if images != 1 else ''} generated."


_HL_FUNCTIONS = {
    "research":   _hl_research,
    "design":     _hl_design,
    "approval":   _hl_approval,
    "factory":    _hl_factory,
    "analytics":  _hl_analytics,
    "pricing":    _hl_pricing,
    "shop_health": _hl_shop_health,
    "cs":         _hl_cs,
    "monitoring": _hl_monitoring,
    "media_bay":  _hl_media_bay,
    "armory":     _hl_armory,
    "radar_bay":  _hl_radar_bay,
    "memory":     _hl_memory,
    "treasury":   _hl_treasury,
}

ALL_ROOMS = list(_HL_FUNCTIONS.keys())


def _build_room_highlights(reports: dict) -> dict[str, str]:
    highlights = {}
    for room, fn in _HL_FUNCTIONS.items():
        r = reports.get(room)
        if r:
            try:
                highlights[room] = fn(r)
            except Exception as e:
                highlights[room] = f"Error generating highlight: {e}"
        else:
            highlights[room] = "No report available."
    return highlights


# ── Summarise functions for LLM briefing ─────────────────────────────────────

def _summarise_analytics(r: dict) -> str:
    lines = [
        f"ANALYTICS — {r.get('report_date', 'unknown')}",
        f"  Products: {r.get('products_active', 0)} active / {r.get('products_total', 0)} total",
        f"  Orders: {r.get('orders_total', 0)} | Revenue: ${r.get('revenue_total', '0')}",
    ]
    top = r.get("top_products", [])
    if top:
        lines.append(f"  Top product: {top[0].get('title', '?')} ({top[0].get('orders', 0)} orders)")
    return "\n".join(lines)


def _summarise_pricing(r: dict) -> str:
    stats = r.get("product_stats", [])
    repricing = [s for s in stats if s.get("recommendation", "KEEP") != "KEEP"]
    lines = [
        f"PRICING — {r.get('run_date', 'unknown')}",
        f"  Products analysed: {r.get('products_analysed', 0)} | Repricing needed: {len(repricing)}",
    ]
    for s in repricing[:3]:
        lines.append(f"  {s.get('title', '?')[:30]} — {s.get('recommendation', '?')} (${s.get('current_price', '?')})")
    return "\n".join(lines)


def _summarise_shop_health(r: dict) -> str:
    products = r.get("products", [])
    critical = [p for p in products if p.get("severity") == "critical"]
    lines = [
        f"SHOP HEALTH — {r.get('run_date', 'unknown')}",
        f"  Scanned: {r.get('products_scanned', 0)} | Flagged: {r.get('flagged_count', 0)} | Critical: {len(critical)}",
    ]
    for p in critical[:3]:
        lines.append(f"  CRITICAL — {p.get('title', '?')[:30]}: {', '.join(p.get('issues', [])[:2])}")
    return "\n".join(lines)


def _summarise_cs(r: dict) -> str:
    attention = r.get("attention_orders", [])
    lines = [
        f"CS — {r.get('run_date', 'unknown')}",
        f"  Orders scanned: {r.get('orders_scanned', 0)} | Attention: {len(attention)}",
    ]
    for o in attention[:2]:
        lines.append(f"  ATTENTION — Order {o.get('order_number', '?')}: {o.get('issue_label', '?')}")
    return "\n".join(lines)


def _summarise_monitoring(r: dict) -> str:
    alerts = r.get("alerts", [])
    return (
        f"MONITORING — overall: {r.get('overall_status', '?').upper()}\n"
        + (f"  Alerts: {'; '.join(str(a)[:60] for a in alerts[:3])}" if alerts else "  All systems healthy.")
    )


def _summarise_simple(room: str, r: dict, fn) -> str:
    return f"{room.upper().replace('_', ' ')} — {fn(r)}"


def _build_briefing(reports: dict) -> str:
    sections = []
    # Core business rooms — detailed summaries
    for room, fn in [
        ("analytics", _summarise_analytics),
        ("pricing", _summarise_pricing),
        ("shop_health", _summarise_shop_health),
        ("cs", _summarise_cs),
        ("monitoring", _summarise_monitoring),
    ]:
        r = reports.get(room)
        sections.append(fn(r) if r else f"{room.upper()} — no report available")

    # Pipeline rooms — one-line highlights
    for room in ["research", "design", "approval", "factory", "treasury", "media_bay", "armory", "radar_bay", "memory"]:
        r = reports.get(room)
        fn = _HL_FUNCTIONS.get(room)
        if r and fn:
            sections.append(f"{room.upper().replace('_', ' ')} — {fn(r)}")
        else:
            sections.append(f"{room.upper().replace('_', ' ')} — no report available")

    return "\n\n".join(sections)


def _save_report(data: dict) -> str:
    os.makedirs(WAR_ROOM_DIR, exist_ok=True)

    latest_path = os.path.join(WAR_ROOM_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.now(_CST).strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(WAR_ROOM_DIR, f"war_room_{ts}.md")

    fix_md    = "\n".join(f"- {i}" for i in data.get("fix", []))    or "- None"
    launch_md = "\n".join(f"- {i}" for i in data.get("launch", [])) or "- None"
    watch_md  = "\n".join(f"- {i}" for i in data.get("watch", []))  or "- None"

    highlights = data.get("room_highlights", {})
    hl_md = "\n".join(f"**{r.replace('_', ' ').title()}:** {h}" for r, h in highlights.items())

    md = f"""# War Room Report — {data['run_date']}

## Executive Summary
{data.get('summary', '')}

## Fix (Urgent)
{fix_md}

## Launch (Growth)
{launch_md}

## Watch (Monitor)
{watch_md}

## Room Highlights
{hl_md}

---
Model: {data.get('model_used', '—')} | Rooms: {len(data.get('rooms_included', []))}
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
    reports = {room: _load_room_report(room) for room in ALL_ROOMS}

    briefing = _build_briefing(reports)
    room_highlights = _build_room_highlights(reports)
    system = load_system_prompt("war_room", "strategist", _WAR_ROOM_FALLBACK)

    prompt = f"""Here is the overnight status across all 14 active rooms:

{briefing}

Synthesise this into a prioritised action plan. Output only the JSON specified."""

    try:
        raw = await call_claude_haiku(prompt, system=system, room="war_room")
        model_used = "haiku"
    except Exception:
        raw = await call_claude_haiku(prompt, system=system, room="warroom")
        model_used = "claude"

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
        "run_date":       datetime.now(_CST).strftime("%Y-%m-%d %H:%M"),
        "model_used":     model_used,
        "summary":        plan.get("summary", ""),
        "fix":            _flatten(plan.get("fix", [])),
        "launch":         _flatten(plan.get("launch", [])),
        "watch":          _flatten(plan.get("watch", [])),
        "room_highlights": room_highlights,
        "rooms_included": [k for k, v in reports.items() if v is not None],
    }

    data["report_path"] = _save_report(data)
    return data
