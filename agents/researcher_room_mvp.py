import os
import json
import re
import asyncio
import httpx
from datetime import datetime, timezone
from agents.llm_client import call_claude
from agents.market_intel import gather_trends, get_seasonal_context
from agents.product_catalog import PRODUCT_TYPES
from agents.brain import load_system_prompt
from agents.notify import notify

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
CONFIG_PATH = os.path.join(BRAIN_PATH, "rooms", "research", "research_config.json")

_SYSTEM_FALLBACK = """You are a print-on-demand market researcher. Find niches that sell well on Etsy and Shopify across a range of product types — not just apparel. Return ONLY a valid JSON object with these exact keys:

- niche: short name for the niche (e.g. "Axolotl Lovers", "Nurse Humor")
- product_type: MUST be one of: {', '.join(f'"{p}"' for p in PRODUCT_TYPES)}
- target_audience: who buys this (e.g. "nurses who love dark humor gift exchanges")
- keywords: list of 5 search keywords (array of strings)
- design_direction: one sentence describing what the design should look like — be specific about art style, subject, and any text/slogan

The market intelligence report ranks product types by current Etsy performance. Follow that ranking — pick the product type with the strongest market signal for the niche you've chosen. Do not default to apparel if another product type is outperforming it."""


def _parse_brief(raw: str) -> dict:
    def _extract(text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    data = _extract(raw)
    if not data:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        data = _extract(match.group()) if match else None
    if not data:
        raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]}")

    # Normalise common alternative key names LLMs return
    key_aliases = {
        "niche":            ["niche", "niche_name", "title", "name"],
        "product_type":     ["product_type", "product", "type"],
        "target_audience":  ["target_audience", "audience", "target"],
        "keywords":         ["keywords", "tags", "search_terms"],
        "design_direction": ["design_direction", "design", "direction", "description"],
    }
    normalised = {}
    for canonical, aliases in key_aliases.items():
        for alias in aliases:
            if alias in data:
                normalised[canonical] = data[alias]
                break
        if canonical not in normalised:
            normalised[canonical] = ""

    if not normalised["niche"]:
        raise ValueError(f"LLM response missing 'niche' key. Keys found: {list(data.keys())}")

    return normalised


def _save_brief(brief: dict) -> str:
    warm_dir = os.path.join(BRAIN_PATH, "rooms", "research", "briefs")
    os.makedirs(warm_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = brief["niche"].lower().replace(" ", "_")[:30]
    filename = f"brief_{timestamp}_{slug}.md"
    filepath = os.path.join(warm_dir, filename)
    content = f"""# Research Brief: {brief['niche']}
Generated: {datetime.utcnow().isoformat()}

## Niche
{brief['niche']}

## Product Type
{brief['product_type']}

## Target Audience
{brief['target_audience']}

## Keywords
{chr(10).join(f'- {kw}' for kw in brief['keywords'])}

## Design Direction
{brief['design_direction']}
"""
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


# ── Config helpers ─────────────────────────────────────────────

def load_config() -> dict:
    defaults = {
        "autonomous": False,
        "delay_minutes": 240,
        "max_per_day": 5,
        "products_today": 0,
        "last_run": None,
        "last_reset_date": None,
    }
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
            return {**defaults, **data}
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults


def save_config(config: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def _cst_today() -> str:
    """Return today's date string in Central Standard Time (UTC-6)."""
    from datetime import timezone, timedelta
    cst = timezone(timedelta(hours=-6))
    return datetime.now(cst).strftime("%Y-%m-%d")

def _reset_if_new_day(config: dict) -> dict:
    today = _cst_today()
    if config.get("last_reset_date") != today:
        config["products_today"] = 0
        config["last_reset_date"] = today
        save_config(config)
    return config


# ── Core researcher ────────────────────────────────────────────

async def run_researcher(input: dict) -> dict:
    """
    Find a profitable niche using live market data + LLM synthesis.

    Input keys (all optional):
      - direction: str — e.g. "something related to cats" or "" for free choice

    Returns:
      - niche, product_type, target_audience, keywords, design_direction
      - brief_path, model_used
    """
    direction = input.get("direction", "").strip()

    # Gather live market data and seasonal context in parallel
    print("[researcher] Fetching market data and seasonal context...")
    market_data, seasonal = await asyncio.gather(
        gather_trends(),
        get_seasonal_context(),
    )

    if market_data:
        print(f"[researcher] Market data ({len(market_data)} chars)")
    else:
        print("[researcher] No market data — using LLM knowledge only")

    if seasonal:
        print(f"[researcher] Seasonal context: {seasonal[:120]}")

    market_section   = f"\n\nLIVE ETSY DATA (what's actually getting favourited right now):\n{market_data}\n" if market_data else ""
    seasonal_section = f"\n\nUPCOMING EVENTS (consider for gifting angle):\n{seasonal}\n" if seasonal else ""

    if direction:
        prompt = f"""Find a profitable print-on-demand niche based on this direction: "{direction}"{market_section}{seasonal_section}
Pick a specific, passionate audience within that space. Use the product type rankings in the market data to choose the best product — follow the signal, don't apply a fixed opinion.
If upcoming events are listed, consider whether a seasonal angle strengthens the niche.
Return the JSON brief."""
    else:
        prompt = f"""Find a profitable print-on-demand niche. Use the live Etsy data below to identify what's actually resonating with buyers right now — the product type rankings show you what's performing strongest this week, follow them.{market_section}{seasonal_section}
Go specific: e.g. "Border Collie agility training enthusiasts" or "ICU Nurse dark humor". Avoid generic niches.
If upcoming events are listed, a seasonal angle can boost sales — but only use it if it genuinely fits the niche.
Return the JSON brief."""

    system = load_system_prompt("research", "researcher", _SYSTEM_FALLBACK).replace(
        "{PRODUCT_TYPES}", ", ".join(f'"{p}"' for p in PRODUCT_TYPES)
    )
    raw = await call_claude(prompt, system=system, room="research")

    brief = _parse_brief(raw)
    brief_path = _save_brief(brief)

    return {
        "niche":            brief["niche"],
        "product_type":     brief["product_type"],
        "target_audience":  brief["target_audience"],
        "keywords":         brief["keywords"],
        "design_direction": brief["design_direction"],
        "brief_path":       brief_path,
        "model_used":       "claude",
    }


# ── Autonomous loop ────────────────────────────────────────────

_loop_task: asyncio.Task | None = None


async def _autonomous_loop() -> None:
    """Background loop: research → trigger designer → sleep → repeat."""
    print("[researcher] Autonomous loop started")
    while True:
        config = load_config()
        if not config.get("autonomous"):
            print("[researcher] Autonomous mode disabled — loop exiting")
            break

        config = _reset_if_new_day(config)

        if config["products_today"] >= config["max_per_day"]:
            # Wait until midnight CST (UTC-6) then reset
            from datetime import timezone, timedelta
            cst = timezone(timedelta(hours=-6))
            now_cst = datetime.now(cst)
            next_midnight_cst = (now_cst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            seconds_until_midnight = int((next_midnight_cst - now_cst).total_seconds())
            print(f"[researcher] Daily cap reached ({config['max_per_day']}). Sleeping until midnight CST ({seconds_until_midnight}s)")
            await asyncio.sleep(seconds_until_midnight + 5)
            config = _reset_if_new_day(load_config())

        print(f"[researcher] Running cycle {config['products_today'] + 1}/{config['max_per_day']}")
        try:
            brief = await run_researcher({})

            config = load_config()
            config["products_today"] = config.get("products_today", 0) + 1
            config["last_run"] = datetime.utcnow().isoformat()
            save_config(config)

            # Trigger designer if auto mode is enabled (best-effort — if it fails, loop continues)
            try:
                async with httpx.AsyncClient(timeout=600) as client:
                    r = await client.post(
                        "http://localhost:9000/api/rooms/design/run",
                        json=brief,
                    )
                    if r.status_code == 200:
                        print(f"[researcher] Design triggered for: {brief['niche']}")
                    else:
                        print(f"[researcher] Design trigger failed: {r.status_code}")
                        await notify(f"⚠️ Designer failed to start for: {brief.get('niche', '?')}\nStatus {r.status_code}")
            except Exception as e:
                print(f"[researcher] Could not trigger designer: {e}")
                await notify(f"⚠️ Designer failed to start for: {brief.get('niche', '?')}\n{str(e)[:120]}")

        except Exception as e:
            print(f"[researcher] Cycle error: {e}")
            await notify(f"⚠️ Researcher cycle error: {str(e)[:120]}")

        delay = config.get("delay_minutes", 240) * 60
        print(f"[researcher] Sleeping {config.get('delay_minutes', 240)} minutes until next cycle")
        await asyncio.sleep(delay)


def start_loop() -> bool:
    """Start the autonomous loop as a background task. Returns True if started."""
    global _loop_task
    if _loop_task and not _loop_task.done():
        return False  # already running
    config = load_config()
    config["autonomous"] = True
    save_config(config)
    _loop_task = asyncio.create_task(_autonomous_loop())
    return True


def stop_loop() -> bool:
    """Stop the autonomous loop. Returns True if it was running."""
    global _loop_task
    config = load_config()
    config["autonomous"] = False
    save_config(config)
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
        _loop_task = None
        return True
    return False


def loop_status() -> dict:
    """Return current autonomous loop status for the UI."""
    global _loop_task
    config = load_config()
    config = _reset_if_new_day(config)
    running = _loop_task is not None and not _loop_task.done()

    next_run_seconds = None
    if running:
        cap_hit = config.get("products_today", 0) >= config.get("max_per_day", 5)
        if cap_hit:
            # Sleeping until midnight CST — show time until reset
            from datetime import timezone, timedelta
            cst = timezone(timedelta(hours=-6))
            now_cst = datetime.now(cst)
            next_midnight = (now_cst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            next_run_seconds = max(0, int((next_midnight - now_cst).total_seconds()))
        elif config.get("last_run"):
            try:
                last = datetime.fromisoformat(config["last_run"])
                elapsed = (datetime.utcnow() - last).total_seconds()
                delay = config["delay_minutes"] * 60
                next_run_seconds = max(0, int(delay - elapsed))
            except Exception:
                pass

    return {
        "running":           running,
        "autonomous":        config.get("autonomous", False),
        "delay_minutes":     config.get("delay_minutes", 240),
        "max_per_day":       config.get("max_per_day", 5),
        "products_today":    config.get("products_today", 0),
        "last_run":          config.get("last_run"),
        "next_run_seconds":  next_run_seconds,
    }


def researcher_midnight_report() -> dict:
    """Scan today's brief files and save a midnight report."""
    from datetime import timezone, timedelta
    cst = timezone(timedelta(hours=-6))
    today_start = datetime.now(cst).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_str = datetime.now(cst).strftime("%Y-%m-%d")

    config = load_config()
    briefs_dir = os.path.join(BRAIN_PATH, "rooms", "research", "briefs")
    report_dir = os.path.join(BRAIN_PATH, "rooms", "research", "reports")

    today_briefs = []
    if os.path.isdir(briefs_dir):
        for fname in sorted(os.listdir(briefs_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(briefs_dir, fname)
            if os.path.getmtime(fpath) < today_start:
                continue
            niche, product_type = "", ""
            try:
                lines = open(fpath).read().splitlines()
                for i, line in enumerate(lines):
                    if line.strip() == "## Niche" and i + 1 < len(lines):
                        niche = lines[i + 1].strip()
                    elif line.strip() == "## Product Type" and i + 1 < len(lines):
                        product_type = lines[i + 1].strip()
            except Exception:
                pass
            today_briefs.append({"niche": niche or fname, "product_type": product_type})

    nothing = not today_briefs
    data = {
        "run_date":         today_str,
        "nothing_to_report": nothing,
        "reason":           ("autonomous mode off" if not config.get("autonomous") else "0 cycles ran today") if nothing else None,
        "autonomous":       config.get("autonomous", False),
        "cycles_run":       len(today_briefs),
        "max_per_day":      config.get("max_per_day", 5),
        "briefs":           today_briefs,
    }

    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "latest_report.json"), "w") as f:
        json.dump(data, f, indent=2)

    return data
