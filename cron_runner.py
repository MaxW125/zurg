#!/opt/homebrew/bin/python3
"""
Zurg cron runner — single entry point for all scheduled jobs.

All cron logic lives here. Do not add cron-related code elsewhere.

Scheduled jobs (set in system crontab — run `crontab -e` to view):
  war_room    daily 7am
  ceo         daily 8am  (reads room reports, sends briefing to owner)
  analytics   daily midnight
  pricing     Monday 6am
  shop_health Sunday + Wednesday 6am
  radar_bay   Sunday 6am

Usage:
  cron_runner.py --job <job_name>

Reporting modes (set by texting Zurg):
  daily   — Zurg texts you a briefing every morning at 8am
  weekly  — Zurg accumulates Mon–Sat, sends one summary Sunday 8am
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

sys.path.insert(0, "~/zurg")

from dotenv import load_dotenv
load_dotenv("~/zurg/.env")

BRAIN_PATH = os.getenv("BRAIN_PATH", "~/Documents/Obsidian Vaults/Zurg")
BASE_URL = "http://localhost:9000"

REPORTING_CONFIG = Path(BRAIN_PATH) / "rooms" / "captain" / "reporting_config.json"
WEEKLY_LOG       = Path(BRAIN_PATH) / "rooms" / "captain" / "weekly_briefings.json"

LOG_PATH = Path("~/zurg/logs/cron.log")
LOG_PATH.parent.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("cron")

ROOM_ENDPOINTS = {
    "war_room":   "/api/war-room/run",
    "analytics":  "/api/analytics/run",
    "pricing":    "/api/pricing/run",
    "shop_health": "/api/shop-health/run",
    "radar_bay":  "/api/radar-bay/run",
}

ROOM_LABELS = {
    "war_room":   "War Room",
    "analytics":  "Analytics",
    "pricing":    "Pricing",
    "shop_health": "Shop Health",
    "radar_bay":  "Radar Bay",
}

# Rooms included in CEO briefing, in priority order
BRIEFING_ROOMS = ["war_room", "analytics", "pricing", "shop_health", "radar_bay"]


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _post(endpoint: str, payload: dict = None) -> dict:
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"error": str(e)}


# ── Notifications ─────────────────────────────────────────────────────────────

def _notify(message: str):
    from agents.notify import notify
    asyncio.run(notify(message))


def _alert_ceo(message: str):
    """Route a critical alert through the CEO so it reaches the owner in Zurg's voice."""
    log.warning(f"Alerting CEO: {message}")
    result = _post("/api/chat/ceo/instruct", {
        "message": f"URGENT: {message}. Alert the owner immediately.",
        "source": "cron_alert",
    })
    response = result.get("response", "")
    if response:
        _notify(response)


# ── Error detection ───────────────────────────────────────────────────────────

def _critical_error(response: dict, label: str) -> str | None:
    """Returns an alert string if the response signals a critical failure, else None."""
    if response.get("error"):
        return f"{label} failed: {response['error'][:200]}"
    s = json.dumps(response).lower()
    if any(p in s for p in ["401", "403", "unauthorized", "token expired"]) and \
       any(p in s for p in ["error", "failed", "exception"]):
        return f"{label} returned an auth error — token may have expired"
    return None


# ── Vault reads ───────────────────────────────────────────────────────────────

def _load_room_report(room: str) -> dict | None:
    path = Path(BRAIN_PATH) / "rooms" / room / "reports" / "latest_report.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _build_briefing_context() -> str:
    """Read latest reports from all briefing rooms and format them for the CEO prompt."""
    sections = []
    for room in BRIEFING_ROOMS:
        label = ROOM_LABELS[room]
        report = _load_room_report(room)
        if not report:
            sections.append(f"[{label}: no report available]")
            continue
        # Truncate large reports — CEO needs the gist, not every field
        summary = json.dumps(report, indent=2)[:1000]
        sections.append(f"--- {label} ---\n{summary}")
    return "\n\n".join(sections)


# ── Reporting config + weekly log ─────────────────────────────────────────────

def _reporting_mode() -> str:
    try:
        return json.loads(REPORTING_CONFIG.read_text()).get("mode", "daily")
    except Exception:
        return "daily"


def _load_weekly_log() -> list:
    try:
        return json.loads(WEEKLY_LOG.read_text())
    except Exception:
        return []


def _append_weekly_log(briefing: str):
    entries = _load_weekly_log()
    entries.append({"date": date.today().isoformat(), "briefing": briefing})
    WEEKLY_LOG.write_text(json.dumps(entries, indent=2))


def _clear_weekly_log():
    WEEKLY_LOG.write_text("[]")


# ── Jobs ──────────────────────────────────────────────────────────────────────

def run_room_job(job: str):
    label = ROOM_LABELS[job]
    log.info(f"Starting {label}")
    result = _post(ROOM_ENDPOINTS[job])
    log.info(f"{label} complete: {json.dumps(result)[:200]}")

    alert = _critical_error(result, label)
    if alert:
        _alert_ceo(alert)


def run_ceo_briefing():
    mode = _reporting_mode()
    today = date.today().weekday()  # 0=Mon … 6=Sun
    context = _build_briefing_context()

    if mode == "daily":
        prompt = (
            "Daily briefing for the owner. Here are the latest reports from all rooms:\n\n"
            f"{context}\n\n"
            "Synthesise into a concise daily briefing. Lead with what matters most: "
            "what's working, what needs attention, what actions were taken. "
            "Write as Zurg — direct, no fluff."
        )
        result = _post("/api/chat/ceo/instruct", {"message": prompt, "source": "cron_briefing"})
        response = result.get("response", "")
        if response:
            _notify(response)
        log.info(f"Daily briefing sent: {response[:120]}")

    else:  # weekly
        if today != 6:  # Mon–Sat: accumulate
            prompt = (
                "Internal daily synthesis — not for the owner yet. "
                "Here are today's room reports:\n\n"
                f"{context}\n\n"
                "Write a concise daily summary of what happened across all rooms today. "
                "This will be compiled into the owner's Sunday weekly report."
            )
            result = _post("/api/chat/ceo/instruct", {"message": prompt, "source": "cron_accumulate"})
            response = result.get("response", "")
            if response:
                _append_weekly_log(response)
            log.info(f"Weekly log updated (weekday {today}): {response[:120]}")

        else:  # Sunday: send the full week
            entries = _load_weekly_log()
            if entries:
                days_text = "\n\n".join(f"[{e['date']}]\n{e['briefing']}" for e in entries)
                combined = f"Daily summaries from the past week:\n\n{days_text}\n\nToday's room reports:\n\n{context}"
            else:
                combined = f"No accumulated daily summaries found. Using today's data only:\n\n{context}"

            prompt = (
                "Weekly briefing for the owner. Here is a summary of the entire week:\n\n"
                f"{combined}\n\n"
                "Synthesise into a comprehensive weekly report: what happened across all rooms, "
                "what improved, what needs attention, and what to focus on next week. "
                "Write as Zurg. Be thorough but clear."
            )
            result = _post("/api/chat/ceo/instruct", {"message": prompt, "source": "cron_briefing"})
            response = result.get("response", "")
            if response:
                _notify(response)
                _clear_weekly_log()
            log.info(f"Weekly briefing sent: {response[:120]}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zurg scheduled job runner")
    parser.add_argument("--job", required=True, choices=list(ROOM_ENDPOINTS.keys()) + ["ceo"])
    args = parser.parse_args()

    log.info(f"=== cron: {args.job} ===")
    try:
        if args.job == "ceo":
            run_ceo_briefing()
        else:
            run_room_job(args.job)
    except Exception as e:
        log.exception(f"Cron job '{args.job}' crashed: {e}")
        _alert_ceo(f"Cron job '{args.job}' crashed: {str(e)[:200]}")
    log.info(f"=== done: {args.job} ===")
