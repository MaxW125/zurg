import os
import json
import re
from datetime import datetime
from agents.llm_client import call_claude
from agents.brain import load_system_prompt

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
RADAR_DIR = os.path.join(BRAIN_PATH, "rooms", "radar_bay", "reports")

_RADAR_FALLBACK = """You are the Radar Agent for a print-on-demand AI business run by Zurg (CEO).
Your job is to scan all active rooms' reports, spot systemic patterns, and propose numbered improvements for the system.
Rules:
- You are a diagnostic tool, not an executor. Propose ideas only — never claim to take action.
- Be specific: name the room, the metric, the gap you spotted.
- Prioritise ruthlessly: priority 1 = broken or losing money now, 5 = nice-to-have.
- Each proposal title must be under 12 words.
- Each description must be 1–2 sentences max.
- Each rationale must reference actual data from the briefing.
- Output EXACTLY this JSON structure, nothing else:
{
  "proposals": [
    {
      "id": 1,
      "title": "<short title>",
      "room": "<room key>",
      "priority": <1-5>,
      "description": "<what to do>",
      "rationale": "<why, citing data>"
    }
  ]
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


def _report_age_hours(room: str) -> float | None:
    path = os.path.join(BRAIN_PATH, "rooms", room, "reports", "latest_report.json")
    if not os.path.exists(path):
        return None
    age = (datetime.utcnow().timestamp() - os.path.getmtime(path)) / 3600
    return round(age, 1)


def _count_files(directory: str) -> int:
    if not os.path.exists(directory):
        return 0
    return len([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])


def _summarise_analytics(r: dict) -> str:
    lines = [f"ANALYTICS (age: {_report_age_hours('analytics')}h)"]
    lines.append(f"  Products: {r.get('products_active', 0)} active / {r.get('products_total', 0)} total")
    lines.append(f"  Orders: {r.get('orders_total', 0)} | Revenue: ${r.get('revenue_total', '0')}")
    top = r.get("top_products", [])
    if top:
        lines.append(f"  Top product: {top[0].get('title', '?')} ({top[0].get('orders', 0)} orders)")
    insights = r.get("insights", "")
    if insights:
        lines.append(f"  Insights: {str(insights)[:200]}")
    return "\n".join(lines)


def _summarise_pricing(r: dict) -> str:
    lines = [f"PRICING (age: {_report_age_hours('pricing')}h)"]
    lines.append(f"  Products analysed: {r.get('products_analysed', 0)}")
    stats = r.get("product_stats", [])
    actions = {"RAISE": 0, "LOWER": 0, "KEEP": 0}
    for s in stats:
        rec = s.get("recommendation", "KEEP").upper()
        if rec in actions:
            actions[rec] += 1
    lines.append(f"  RAISE: {actions['RAISE']} | LOWER: {actions['LOWER']} | KEEP: {actions['KEEP']}")
    return "\n".join(lines)


def _summarise_shop_health(r: dict) -> str:
    products = r.get("products", [])
    critical = [p for p in products if p.get("severity") == "critical"]
    warning = [p for p in products if p.get("severity") == "warning"]
    lines = [f"SHOP HEALTH (age: {_report_age_hours('shop_health')}h)"]
    lines.append(f"  Scanned: {r.get('products_scanned', 0)} | Flagged: {r.get('flagged_count', 0)}")
    lines.append(f"  Critical: {len(critical)} | Warnings: {len(warning)}")
    for p in critical[:2]:
        lines.append(f"  CRITICAL — {p.get('title', '?')}: {', '.join(p.get('issues', []))}")
    return "\n".join(lines)


def _summarise_cs(r: dict) -> str:
    attention = r.get("attention_orders", [])
    review_q = r.get("review_queue", [])
    lines = [f"CS (age: {_report_age_hours('cs')}h)"]
    lines.append(f"  Orders scanned: {r.get('orders_scanned', 0)}")
    lines.append(f"  Needs attention: {len(attention)} | Review requests ready: {len(review_q)}")
    return "\n".join(lines)


def _summarise_war_room(r: dict) -> str:
    lines = [f"WAR ROOM (age: {_report_age_hours('war_room')}h)"]
    lines.append(f"  Fix items: {len(r.get('fix', []))} | Launch items: {len(r.get('launch', []))} | Watch: {len(r.get('watch', []))}")
    summary = r.get("summary", "")
    if summary:
        lines.append(f"  Summary: {str(summary)[:200]}")
    return "\n".join(lines)


def _summarise_monitoring(r: dict) -> str:
    systems = r.get("systems", [])
    alerts = r.get("alerts", [])
    lines = [f"MONITORING (age: {_report_age_hours('monitoring')}h)"]
    lines.append(f"  Overall: {r.get('overall_status', '?').upper()}")
    lines.append(f"  Systems checked: {len(systems)} | Alerts: {len(alerts)}")
    for a in alerts[:3]:
        lines.append(f"  ALERT — {a}")
    return "\n".join(lines)


def _summarise_media_bay(r: dict) -> str:
    lines = [f"MEDIA BAY (age: {_report_age_hours('media_bay')}h)"]
    lines.append(f"  Last product: {r.get('product_title', '?')}")
    lines.append(f"  Publer scheduled: {r.get('publer_scheduled', False)}")
    return "\n".join(lines)


def _build_briefing(reports: dict) -> str:
    sections = []

    # Research pipeline metrics
    briefs_dir = os.path.join(BRAIN_PATH, "rooms", "research", "briefs")
    verdicts_dir = os.path.join(BRAIN_PATH, "rooms", "approval", "verdicts")
    brief_count = _count_files(briefs_dir)
    verdict_count = _count_files(verdicts_dir)
    sections.append(
        f"PIPELINE METRICS\n"
        f"  Research briefs generated: {brief_count}\n"
        f"  Approval verdicts collected: {verdict_count} "
        f"({'Phase 1 — owner approves all' if verdict_count < 100 else 'Phase 2+'})"
    )

    room_summaries = {
        "analytics":   (_summarise_analytics,   "ANALYTICS"),
        "pricing":     (_summarise_pricing,      "PRICING"),
        "shop_health": (_summarise_shop_health,  "SHOP HEALTH"),
        "cs":          (_summarise_cs,           "CS"),
        "war_room":    (_summarise_war_room,     "WAR ROOM"),
        "monitoring":  (_summarise_monitoring,   "MONITORING"),
        "media_bay":   (_summarise_media_bay,    "MEDIA BAY"),
    }

    for key, (fn, label) in room_summaries.items():
        r = reports.get(key)
        if r:
            sections.append(fn(r))
        else:
            sections.append(f"{label} — no report available (never run or file missing)")

    return "\n\n".join(sections)


def _save_report(data: dict) -> str:
    os.makedirs(RADAR_DIR, exist_ok=True)

    latest_path = os.path.join(RADAR_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(RADAR_DIR, f"radar_bay_{ts}.md")

    props_md = ""
    for p in data.get("proposals", []):
        priority_label = ["", "CRITICAL", "HIGH", "MEDIUM", "LOW", "NICE-TO-HAVE"][p.get("priority", 3)]
        props_md += f"### #{p['id']} [{priority_label}] {p['title']}\n"
        props_md += f"**Room:** {p.get('room', '?')}  \n"
        props_md += f"**Description:** {p.get('description', '')}  \n"
        props_md += f"**Rationale:** {p.get('rationale', '')}  \n\n"

    md = f"""# Radar Bay Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC

## Proposals ({len(data.get('proposals', []))})

{props_md.strip()}

---
Rooms scanned: {', '.join(data.get('rooms_scanned', []))}
Model: {data.get('model_used', '—')}
"""
    with open(md_path, "w") as f:
        f.write(md)

    return md_path


async def get_latest_report() -> dict | None:
    path = os.path.join(RADAR_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_radar_bay() -> dict:
    room_keys = ["analytics", "pricing", "shop_health", "cs", "war_room", "monitoring", "media_bay"]
    reports = {k: _load_room_report(k) for k in room_keys}
    rooms_scanned = [k for k, v in reports.items() if v is not None]

    briefing = _build_briefing(reports)
    system = load_system_prompt("radar_bay", "radar", _RADAR_FALLBACK)

    prompt = f"""Here is a full diagnostic briefing of the Zurg AI business system:

{briefing}

Analyse this and produce a prioritised list of improvement proposals. Focus on:
- Rooms with missing or stale reports (>24h old)
- Pipeline gaps (e.g. low verdict count blocking Approval Engine progress)
- Data quality issues spotted in reports (thin briefs, low product count, no sales)
- Recurring alert patterns from Monitoring
- War Room fix items that have appeared across multiple scans
- Any room that has never been run

Output only the JSON specified."""

    try:
        raw = await call_claude(prompt, system=system, room="radar")
    except Exception:
        raw = await call_claude(prompt, system=system, room="radarbay")
        model_used = "claude"

    # Try object form first {"proposals": [...]}, then bare array [...]
    parsed = None
    m_obj = re.search(r'\{[\s\S]*\}', raw)
    if m_obj:
        try:
            candidate = json.loads(m_obj.group(0))
            if "proposals" in candidate:
                parsed = candidate
        except Exception:
            pass
    if parsed is None:
        m_arr = re.search(r'\[[\s\S]*\]', raw)
        if m_arr:
            try:
                arr = json.loads(m_arr.group(0))
                if isinstance(arr, list):
                    parsed = {"proposals": arr}
            except Exception:
                pass
    if parsed is None:
        parsed = {"proposals": [{"id": 1, "title": "No structured output from LLM", "room": "system", "priority": 1, "description": raw[:300], "rationale": "LLM did not return expected JSON"}]}

    proposals = parsed.get("proposals", [])
    # Ensure all fields are strings/ints
    for i, p in enumerate(proposals):
        p["id"] = p.get("id", i + 1)
        p["title"] = str(p.get("title", ""))
        # LLM sometimes uses affectedRoom or affected_room instead of room
        p["room"] = str(p.get("room") or p.get("affectedRoom") or p.get("affected_room") or "system")
        p["priority"] = int(p.get("priority", 3))
        p["description"] = str(p.get("description", ""))
        p["rationale"] = str(p.get("rationale", ""))

    data = {
        "run_date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "model_used": model_used,
        "rooms_scanned": rooms_scanned,
        "proposals": proposals,
    }

    data["report_path"] = _save_report(data)
    return data
