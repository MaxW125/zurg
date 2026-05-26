#!/opt/homebrew/bin/python3
"""
Zurg cron runner — single entry point for all scheduled jobs.

All cron logic lives here. Do not add cron-related code elsewhere.

Scheduled jobs (set in system crontab — run `crontab -e` to view):
  midnight   0:00am daily — all 14 rooms generate overnight reports
  war_room   0:30am daily — synthesises all room reports into action plan
  briefing   8:00am daily — reads war_room report, sends to owner via WhatsApp

Usage:
  cron_runner.py --job <job_name>
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

_CST = timezone(timedelta(hours=-6))

sys.path.insert(0, "~/zurg")

from dotenv import load_dotenv
load_dotenv("~/zurg/.env")

BRAIN_PATH = os.getenv("BRAIN_PATH", "~/Documents/Obsidian Vaults/Zurg")
BASE_URL = "http://localhost:9000"

LOG_PATH = Path("~/zurg/logs/cron.log")
LOG_PATH.parent.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("cron")

# All midnight endpoints — passive rooms use /midnight-report, active rooms use /run
MIDNIGHT_ENDPOINTS = {
    "research":   "/api/rooms/research/midnight-report",
    "design":     "/api/rooms/design/midnight-report",
    "approval":   "/api/rooms/approval/midnight-report",
    "factory":    "/api/rooms/factory/midnight-report",
    "armory":     "/api/armory/midnight-report",
    "memory":     "/api/memory/midnight-report",
    "treasury":   "/api/treasury/midnight-report",
    "media_bay":  "/api/media-bay/midnight-report",
    "analytics":  "/api/analytics/run",
    "pricing":    "/api/pricing/run",
    "shop_health": "/api/shop-health/run",
    "cs":         "/api/cs/run",
    "monitoring": "/api/monitoring/run",
    "radar_bay":  "/api/radar-bay/run",
}


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _post(endpoint: str, payload: dict = None, timeout: int = 300) -> dict:
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
    except Exception as e:
        return {"error": str(e)}


# ── Notifications ─────────────────────────────────────────────────────────────

def _notify(message: str):
    import asyncio
    from agents.notify import notify
    asyncio.run(notify(message))


def _alert_ceo(message: str):
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
    if response.get("error"):
        return f"{label} failed: {response['error'][:200]}"
    s = json.dumps(response).lower()
    if any(p in s for p in ["401", "403", "unauthorized", "token expired"]) and \
       any(p in s for p in ["error", "failed", "exception"]):
        return f"{label} returned an auth error — token may have expired"
    return None


# ── Jobs ──────────────────────────────────────────────────────────────────────

def _call_room(name: str, endpoint: str) -> tuple[str, dict]:
    result = _post(endpoint, timeout=300)
    return name, result


def run_midnight_job():
    """Call all 14 room endpoints concurrently and log results."""
    log.info("=== midnight: starting all 14 rooms ===")
    errors = []

    with ThreadPoolExecutor(max_workers=14) as pool:
        futures = {
            pool.submit(_call_room, name, ep): name
            for name, ep in MIDNIGHT_ENDPOINTS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                room_name, result = future.result(timeout=310)
                alert = _critical_error(result, room_name)
                if alert:
                    errors.append(alert)
                    log.warning(f"midnight/{room_name}: {alert}")
                else:
                    log.info(f"midnight/{room_name}: ok — {json.dumps(result)[:120]}")
            except Exception as e:
                msg = f"{name} raised exception: {str(e)[:120]}"
                errors.append(msg)
                log.error(f"midnight/{name}: {msg}")

    if errors:
        _alert_ceo(f"Midnight job had {len(errors)} error(s): {errors[0]}")
    log.info(f"=== midnight: done ({len(MIDNIGHT_ENDPOINTS)} rooms, {len(errors)} errors) ===")


def run_war_room_job():
    """Run the War Room synthesis after all midnight reports are ready."""
    log.info("Starting War Room synthesis")
    result = _post("/api/war-room/run", timeout=300)
    log.info(f"War Room complete: {json.dumps(result)[:200]}")

    alert = _critical_error(result, "War Room")
    if alert:
        _alert_ceo(alert)


def run_briefing_job():
    """Read the War Room report and send it to the owner via WhatsApp. No LLM call."""
    war_room_path = Path(BRAIN_PATH) / "rooms" / "war_room" / "reports" / "latest_report.json"

    try:
        report = json.loads(war_room_path.read_text())
    except Exception as e:
        log.error(f"Briefing: could not read War Room report: {e}")
        _notify(f"⚠️ Zurg couldn't send today's briefing — War Room report missing. Check logs.")
        return

    run_date = report.get("run_date", datetime.now(_CST).strftime("%Y-%m-%d"))
    summary = report.get("summary", "No summary available.")
    fix_items    = report.get("fix", [])
    launch_items = report.get("launch", [])
    watch_items  = report.get("watch", [])

    fix_str    = "\n".join(f"• {i}" for i in fix_items)    or "• Nothing urgent"
    launch_str = "\n".join(f"• {i}" for i in launch_items) or "• No launches pending"
    watch_str  = "\n".join(f"• {i}" for i in watch_items)  or "• Nothing to monitor"

    rooms_ok = len(report.get("rooms_included", []))

    highlights = report.get("room_highlights", {})
    highlights_str = "\n".join(f"• {r.replace('_',' ').title()}: {h}" for r, h in highlights.items()) or "• No highlights"

    message = (
        f"📊 Daily Briefing — {run_date}\n\n"
        f"{summary}\n\n"
        f"🔥 Fix:\n{fix_str}\n\n"
        f"🚀 Launch:\n{launch_str}\n\n"
        f"👁 Watch:\n{watch_str}\n\n"
        f"📋 Room Highlights:\n{highlights_str}\n\n"
        f"({rooms_ok}/14 rooms reported)"
    )

    _notify(message)
    log.info(f"Briefing sent: {message[:120]}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zurg scheduled job runner")
    parser.add_argument(
        "--job", required=True,
        choices=["midnight", "war_room", "briefing"],
    )
    args = parser.parse_args()

    log.info(f"=== cron: {args.job} ===")
    try:
        if args.job == "midnight":
            run_midnight_job()
        elif args.job == "war_room":
            run_war_room_job()
        elif args.job == "briefing":
            run_briefing_job()
    except Exception as e:
        log.exception(f"Cron job '{args.job}' crashed: {e}")
        _alert_ceo(f"Cron job '{args.job}' crashed: {str(e)[:200]}")
    log.info(f"=== done: {args.job} ===")
