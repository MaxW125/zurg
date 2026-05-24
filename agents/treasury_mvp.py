import os
import json
from datetime import datetime, timezone, timedelta
from agents.brain import load_system_prompt

# All timestamps and daily-cap resets use CST (UTC-6) to stay in sync with the researcher loop
_CST = timezone(timedelta(hours=-6))

def _cst_now() -> datetime:
    return datetime.now(_CST)

def _cst_today() -> str:
    return _cst_now().strftime("%Y-%m-%d")

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
COSTS_LEDGER = os.path.join(BRAIN_PATH, "rooms", "treasury", "costs.jsonl")
CONFIG_PATH  = os.path.join(BRAIN_PATH, "rooms", "treasury", "treasury_config.json")

# Pricing per model (USD per token)
_MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6":         (3.00  / 1_000_000, 15.00 / 1_000_000),
    "claude-haiku-4-5-20251001": (0.80  / 1_000_000,  4.00 / 1_000_000),
}
_DEFAULT_RATES = _MODEL_RATES["claude-sonnet-4-6"]  # safe fallback

DEFAULT_DAILY_CAP = 1.00


def get_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    return {"daily_cap_usd": float(cfg.get("daily_cap_usd", DEFAULT_DAILY_CAP))}


def set_config(daily_cap_usd: float) -> dict:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    cfg = {"daily_cap_usd": round(daily_cap_usd, 4)}
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def append_cost_entry(room: str, model: str, tokens_in: int, tokens_out: int) -> float:
    """Write one cost line to the ledger. Returns cost_usd."""
    rate_in, rate_out = _MODEL_RATES.get(model, _DEFAULT_RATES)
    cost = round(tokens_in * rate_in + tokens_out * rate_out, 6)
    entry = {
        "ts":        _cst_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "room":      room,
        "model":     model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd":  cost,
    }
    os.makedirs(os.path.dirname(COSTS_LEDGER), exist_ok=True)
    with open(COSTS_LEDGER, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return cost


def append_fixed_cost_entry(room: str, label: str, cost_usd: float) -> float:
    """Write a fixed-cost line to the ledger (e.g. Etsy listing fee). Returns cost_usd."""
    entry = {
        "ts":        _cst_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "room":      room,
        "model":     label,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd":  round(cost_usd, 6),
    }
    os.makedirs(os.path.dirname(COSTS_LEDGER), exist_ok=True)
    with open(COSTS_LEDGER, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return cost_usd


def get_today_spend() -> float:
    """Sum cost_usd for all entries where ts starts with today's CST date."""
    today = _cst_today()
    total = 0.0
    try:
        with open(COSTS_LEDGER) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("ts", "").startswith(today):
                        total += float(entry.get("cost_usd", 0))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return round(total, 6)


def check_daily_cap():
    """Raise RuntimeError if today's spend has hit the configured daily cap."""
    cfg = get_config()
    cap = cfg["daily_cap_usd"]
    if cap <= 0:
        return  # 0 = disabled
    spent = get_today_spend()
    if spent >= cap:
        raise RuntimeError(f"daily_cap_exceeded: spent ${spent:.4f} of ${cap:.2f} cap today")


def _read_all_entries() -> list[dict]:
    entries = []
    try:
        with open(COSTS_LEDGER) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return entries


def get_report() -> dict:
    entries = _read_all_entries()
    today = _cst_today()

    total_spend = 0.0
    today_spend = 0.0
    by_room: dict[str, dict] = {}

    for e in entries:
        cost = float(e.get("cost_usd", 0))
        room = e.get("room", "unknown")
        total_spend += cost
        if e.get("ts", "").startswith(today):
            today_spend += cost

        if room not in by_room:
            by_room[room] = {"room": room, "runs": 0, "total_cost": 0.0}
        by_room[room]["runs"] += 1
        by_room[room]["total_cost"] += cost

    # Round by-room totals
    room_rows = sorted(by_room.values(), key=lambda r: -r["total_cost"])
    for r in room_rows:
        r["total_cost"] = round(r["total_cost"], 4)

    total_runs = len(entries)
    avg_cost = round(total_spend / total_runs, 6) if total_runs else 0.0

    # ROI — read revenue from latest analytics report
    revenue = _get_analytics_revenue()
    roi = None
    if revenue is not None and total_spend > 0:
        roi = round(revenue / total_spend, 2)

    cfg = get_config()

    return {
        "total_spend":    round(total_spend, 4),
        "today_spend":    round(today_spend, 4),
        "daily_cap_usd":  cfg["daily_cap_usd"],
        "cap_hit_today":  today_spend >= cfg["daily_cap_usd"] and cfg["daily_cap_usd"] > 0,
        "total_runs":     total_runs,
        "avg_cost":       avg_cost,
        "revenue":        revenue,
        "roi":            roi,
        "by_room":        room_rows,
        "entry_count":    len(entries),
        "report_date":    today,
    }


def treasury_midnight_report() -> dict:
    today = _cst_today()
    cfg = get_config()
    cap = cfg["daily_cap_usd"]

    all_entries = _read_all_entries()
    today_entries = [e for e in all_entries if e.get("ts", "").startswith(today)]

    spend_today = round(sum(float(e.get("cost_usd", 0)) for e in today_entries), 4)
    cap_pct = round(spend_today / cap * 100, 1) if cap > 0 else 0.0

    by_room: dict[str, float] = {}
    images_today = 0
    for e in today_entries:
        room = e.get("room", "unknown")
        by_room[room] = round(by_room.get(room, 0.0) + float(e.get("cost_usd", 0)), 4)
        if e.get("model", "").startswith("imagen"):
            images_today += 1

    top_rooms = sorted(
        [{"room": k, "cost_usd": v} for k, v in by_room.items()],
        key=lambda x: -x["cost_usd"],
    )[:5]

    report_dir = os.path.join(BRAIN_PATH, "rooms", "treasury", "reports")
    data = {
        "run_date":             today,
        "spend_today":          spend_today,
        "daily_cap_usd":        cap,
        "cap_pct":              cap_pct,
        "cap_hit":              spend_today >= cap and cap > 0,
        "total_entries_today":  len(today_entries),
        "images_generated_today": images_today,
        "top_rooms_today":      top_rooms,
    }

    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "latest_report.json"), "w") as f:
        json.dump(data, f, indent=2)

    return data


def _get_analytics_revenue() -> float | None:
    path = os.path.join(BRAIN_PATH, "rooms", "analytics", "reports", "latest_report.json")
    try:
        with open(path) as f:
            data = json.load(f)
        val = data.get("revenue_total")
        if val is not None:
            return float(val)
    except Exception:
        pass
    return None
