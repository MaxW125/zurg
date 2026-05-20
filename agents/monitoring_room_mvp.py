import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
import httpx
from agents.brain import load_system_prompt

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
MONITORING_DIR = os.path.join(BRAIN_PATH, "rooms", "monitoring", "reports")

SHOPIFY_ACCESS_TOKEN    = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_STORE_URL       = os.getenv("SHOPIFY_STORE_URL", "")
ANTHROPIC_API_KEY       = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_HOST             = os.getenv("OLLAMA_HOST", "http://localhost:11434")
PRINTIFY_API_TOKEN      = os.getenv("PRINTIFY_API_TOKEN", "")
PRINTIFY_ETSY_SHOP_ID   = os.getenv("PRINTIFY_ETSY_SHOP_ID", "")
ETSY_API_KEY            = os.getenv("ETSY_API_KEY", "")
ETSY_SHARED_SECRET      = os.getenv("ETSY_SHARED_SECRET", "")
ETSY_SHOP_NAME          = os.getenv("ETSY_SHOP_NAME", "")

SHOPIFY_API_VERSION = "2025-01"
STALE_HOURS = 24

_BUILT_ROOMS = [
    ("analytics",  "Analytics Room"),
    ("pricing",    "Pricing Room"),
    ("shop_health","Shop Health Room"),
    ("cs",         "CS Room"),
    ("war_room",   "War Room"),
]


def _report_age_hours(room_key: str) -> float | None:
    path = os.path.join(BRAIN_PATH, "rooms", room_key, "reports", "latest_report.json")
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    age_seconds = datetime.now(timezone.utc).timestamp() - mtime
    return round(age_seconds / 3600, 1)


async def _check_shopify() -> dict:
    if not SHOPIFY_ACCESS_TOKEN or not SHOPIFY_STORE_URL:
        return {"status": "yellow", "detail": "Credentials not configured"}
    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/shop.json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN})
        if r.status_code == 200:
            return {"status": "green", "detail": "Token valid"}
        if r.status_code == 401:
            return {"status": "red", "detail": "401 — token expired, run the refresh command in vault/rooms/captain/shopify-token.md"}
        return {"status": "yellow", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "red", "detail": f"Connection failed: {str(e)[:80]}"}


async def _check_anthropic() -> dict:
    if not ANTHROPIC_API_KEY:
        return {"status": "yellow", "detail": "ANTHROPIC_API_KEY not set"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
            )
        if r.status_code == 200:
            return {"status": "green", "detail": "API key valid"}
        if r.status_code == 401:
            return {"status": "red", "detail": "401 — API key invalid or revoked"}
        return {"status": "yellow", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "red", "detail": f"Connection failed: {str(e)[:80]}"}


async def _check_etsy_api() -> dict:
    if not ETSY_API_KEY or not ETSY_SHARED_SECRET:
        return {"status": "yellow", "detail": "ETSY_API_KEY / ETSY_SHARED_SECRET not set"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://openapi.etsy.com/v3/application/shops?shop_name={ETSY_SHOP_NAME or 'KrakenAndCoDesigns'}",
                headers={"x-api-key": f"{ETSY_API_KEY}:{ETSY_SHARED_SECRET}"},
            )
        if r.status_code == 200:
            count = r.json().get("count", 0)
            if count:
                shop = r.json()["results"][0]
                listings = shop.get("listing_active_count", "?")
                return {"status": "green", "detail": f"Key valid — {shop['shop_name']}, {listings} active listings"}
            return {"status": "yellow", "detail": "Key valid but shop not found"}
        if r.status_code == 401:
            return {"status": "red", "detail": "401 — API key invalid or expired"}
        return {"status": "yellow", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "red", "detail": f"Connection failed: {str(e)[:80]}"}


async def _check_printify_etsy() -> dict:
    if not PRINTIFY_API_TOKEN:
        return {"status": "yellow", "detail": "PRINTIFY_API_TOKEN not set"}
    if not PRINTIFY_ETSY_SHOP_ID:
        return {"status": "yellow", "detail": "PRINTIFY_ETSY_SHOP_ID not set — Etsy channel not configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.printify.com/v1/shops.json",
                headers={"Authorization": f"Bearer {PRINTIFY_API_TOKEN}"},
            )
        if r.status_code != 200:
            return {"status": "yellow", "detail": f"Printify API HTTP {r.status_code}"}
        shops = r.json()
        etsy_shop = next((s for s in shops if str(s.get("id")) == PRINTIFY_ETSY_SHOP_ID), None)
        if not etsy_shop:
            return {"status": "red", "detail": f"Etsy shop {PRINTIFY_ETSY_SHOP_ID} not found in Printify — reconnect in dashboard"}
        return {"status": "green", "detail": f"Connected — {etsy_shop.get('title', 'Etsy store')}"}
    except Exception as e:
        return {"status": "red", "detail": f"Connection failed: {str(e)[:80]}"}


async def _check_ollama() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
        if r.status_code == 200:
            models = [m.get("name", "") for m in r.json().get("models", [])]
            label = ", ".join(models[:3]) if models else "running (no models)"
            return {"status": "green", "detail": f"Running — {label}"}
        return {"status": "yellow", "detail": f"HTTP {r.status_code}"}
    except Exception:
        return {"status": "yellow", "detail": "Ollama not reachable — Claude fallback will be used"}


def _check_room_report(room_key: str, room_name: str) -> dict:
    age = _report_age_hours(room_key)
    if age is None:
        return {"status": "yellow", "detail": "No report yet — run the room to generate one"}
    if age > STALE_HOURS:
        return {"status": "yellow", "detail": f"Report is {age}h old — consider re-running"}
    return {"status": "green", "detail": f"Report is {age}h old"}


def _overall_status(systems: list[dict]) -> str:
    statuses = [s["status"] for s in systems]
    if "red" in statuses:
        return "red"
    if "yellow" in statuses:
        return "yellow"
    return "green"


def _build_alerts(systems: list[dict]) -> list[str]:
    alerts = []
    for s in systems:
        if s["status"] in ("red", "yellow"):
            alerts.append(f"{s['name']}: {s['detail']}")
    return alerts


def _build_summary(overall: str, alerts: list[str]) -> str:
    if overall == "green":
        return "All systems healthy. No action needed."
    red_count = sum(1 for a in alerts if "401" in a or "expired" in a or "invalid" in a or "Connection failed" in a)
    yellow_count = len(alerts) - red_count
    parts = []
    if red_count:
        parts.append(f"{red_count} critical issue{'s' if red_count > 1 else ''}")
    if yellow_count:
        parts.append(f"{yellow_count} warning{'s' if yellow_count > 1 else ''}")
    return (", ".join(parts) + ". " + alerts[0]) if alerts else "Issues detected."


def _save_report(data: dict) -> str:
    os.makedirs(MONITORING_DIR, exist_ok=True)

    latest_path = os.path.join(MONITORING_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(MONITORING_DIR, f"monitoring_{ts}.md")

    status_icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

    rows = "\n".join(
        f"| {s['name']} | {status_icon.get(s['status'], '?')} {s['status'].upper()} | {s['detail']} |"
        for s in data["systems"]
    )

    alerts_md = "\n".join(f"- {a}" for a in data["alerts"]) or "- None"

    md = f"""# Monitoring Report — {data['checked_at']} UTC

**Overall:** {status_icon.get(data['overall_status'], '?')} {data['overall_status'].upper()}

## Systems

| System | Status | Detail |
|--------|--------|--------|
{rows}

## Alerts
{alerts_md}

## Summary
{data['summary']}
"""
    with open(md_path, "w") as f:
        f.write(md)

    return md_path


async def get_latest_report() -> dict | None:
    path = os.path.join(MONITORING_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_monitoring() -> dict:
    shopify, anthropic, ollama, printify_etsy, etsy_api = await asyncio.gather(
        _check_shopify(),
        _check_anthropic(),
        _check_ollama(),
        _check_printify_etsy(),
        _check_etsy_api(),
    )

    systems = [
        {"name": "Server",           "key": "server",        "status": "green", "detail": "Responding — you're reading this"},
        {"name": "Shopify API",      "key": "shopify",       **shopify},
        {"name": "Printify Etsy",    "key": "printify_etsy", **printify_etsy},
        {"name": "Etsy API",         "key": "etsy_api",      **etsy_api},
        {"name": "Anthropic API",    "key": "anthropic",     **anthropic},
        {"name": "Ollama",           "key": "ollama",        **ollama},
    ]

    for room_key, room_name in _BUILT_ROOMS:
        result = _check_room_report(room_key, room_name)
        systems.append({"name": room_name, "key": room_key, **result})

    overall = _overall_status(systems)
    alerts = _build_alerts(systems)
    summary = _build_summary(overall, alerts)

    data = {
        "checked_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "overall_status": overall,
        "systems": systems,
        "alerts": alerts,
        "summary": summary,
    }

    data["report_path"] = _save_report(data)
    return data
