import os
import json
from datetime import datetime
from agents.llm_client import call_claude_haiku
from agents.brain import load_system_prompt
import httpx

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
MEDIA_BAY_DIR = os.path.join(BRAIN_PATH, "rooms", "media_bay", "reports")
PUBLER_API_KEY = os.getenv("PUBLER_API_KEY", "")
PUBLER_BASE = "https://app.publer.io/api/v1"

_MEDIA_FALLBACK = """You are the Media Agent for a print-on-demand Shopify store.
Your job is to write scroll-stopping short-form social captions for TikTok and Instagram.
Write for a young, trend-aware audience. Be punchy, specific, and fun — never corporate.
Use line breaks for readability. Hooks must create instant curiosity or emotion.
Return output using EXACTLY these labels, in this order:
TIKTOK_HOOK: <one punchy sentence that makes someone stop scrolling>
TIKTOK_CAPTION: <2-3 sentences: expand the hook, describe the vibe, add a CTA>
TIKTOK_HASHTAGS: <15 hashtags separated by spaces, no # prefix in the list — add # when assembling>
INSTAGRAM_HOOK: <one polished sentence — warmer, more visual>
INSTAGRAM_CAPTION: <3-4 sentences: storytell around the product, invoke feeling, end with CTA>
INSTAGRAM_HASHTAGS: <8 hashtags separated by spaces, no # prefix>
No extra text before or after these labels."""


_LABELS = [
    "TIKTOK_HOOK", "TIKTOK_CAPTION", "TIKTOK_HASHTAGS",
    "INSTAGRAM_HOOK", "INSTAGRAM_CAPTION", "INSTAGRAM_HASHTAGS",
]


def _normalize(text: str) -> str:
    """Strip markdown decoration from label lines so each label reads as LABEL: content."""
    import re
    for label in _LABELS:
        # Pass 1: inline format — `**LABEL**:` or `* **LABEL**:` → `LABEL:`
        # Content stays on same line, just strip the markdown around the label+colon
        text = re.sub(rf"[*_]{{0,3}}{label}[*_]{{0,3}}\s*:", f"{label}:", text)
        # Pass 2: block format — `**LABEL**\n` or `### LABEL\n` → `LABEL: `
        # Content on next line; collapse to inline
        text = re.sub(rf"[#*_]{{0,4}}\s*{label}[*_]{{0,3}}\s*\n+", f"{label}: ", text)
    return text


def _parse_content(text: str) -> dict:
    text = _normalize(text)

    def _extract(label: str) -> str:
        marker = f"{label}:"
        idx = text.find(marker)
        if idx == -1:
            return ""
        start = idx + len(marker)
        # find the next label boundary
        next_pos = -1
        for other in _LABELS:
            if other == label:
                continue
            p = text.find(f"{other}:", start)
            if p != -1 and (next_pos == -1 or p < next_pos):
                next_pos = p
        chunk = text[start:next_pos].strip() if next_pos != -1 else text[start:].strip()
        # for single-line fields (HOOK, HASHTAGS) return only the first line
        if "CAPTION" not in label:
            return chunk.split("\n")[0].strip()
        return chunk

    tiktok_hook     = _extract("TIKTOK_HOOK")
    tiktok_body     = _extract("TIKTOK_CAPTION")
    tiktok_tags_raw = _extract("TIKTOK_HASHTAGS")
    ig_hook         = _extract("INSTAGRAM_HOOK")
    ig_body         = _extract("INSTAGRAM_CAPTION")
    ig_tags_raw     = _extract("INSTAGRAM_HASHTAGS")

    def _tags(raw: str) -> list[str]:
        return [f"#{t.lstrip('#').strip()}" for t in raw.replace(",", " ").split() if t.strip()]

    tiktok_tags = _tags(tiktok_tags_raw)[:15]
    ig_tags     = _tags(ig_tags_raw)[:8]

    tiktok_full = f"{tiktok_hook}\n\n{tiktok_body}\n\n{' '.join(tiktok_tags)}"
    ig_full     = f"{ig_hook}\n\n{ig_body}\n\n{' '.join(ig_tags)}"

    return {
        "tiktok": {
            "hook":     tiktok_hook,
            "caption":  tiktok_body,
            "hashtags": tiktok_tags,
            "full_post": tiktok_full.strip(),
        },
        "instagram": {
            "hook":     ig_hook,
            "caption":  ig_body,
            "hashtags": ig_tags,
            "full_post": ig_full.strip(),
        },
    }


async def _generate_content(
    product_title: str,
    product_description: str,
    product_type: str,
    mockup_url: str,
) -> tuple[dict, str]:
    prompt = f"""Create short-form social media content for this print-on-demand product:

PRODUCT TITLE: {product_title}
PRODUCT TYPE: {product_type}
DESCRIPTION: {product_description}
{"MOCKUP IMAGE: " + mockup_url if mockup_url else ""}

Generate TikTok and Instagram captions following the exact format specified in your instructions."""

    system = load_system_prompt("media_bay", "media_agent", _MEDIA_FALLBACK)

    try:
        text = await call_claude_haiku(prompt, system=system, room="media")
        model = "haiku"
    except Exception:
        text = await call_claude_haiku(prompt, system=system, room="mediabay")
        model = "claude"

    content = _parse_content(text)
    return content, model


async def _schedule_publer(
    product_title: str,
    content: dict,
    mockup_url: str,
) -> list[dict]:
    if not PUBLER_API_KEY:
        return []

    results = []
    headers = {
        "Authorization": f"Bearer {PUBLER_API_KEY}",
        "Content-Type": "application/json",
    }

    platforms = [
        {"key": "tiktok",     "text": content["tiktok"]["full_post"]},
        {"key": "instagram",  "text": content["instagram"]["full_post"]},
    ]

    async with httpx.AsyncClient(timeout=15) as client:
        for p in platforms:
            payload: dict = {
                "text":      p["text"],
                "platforms": [p["key"]],
            }
            if mockup_url:
                payload["media"] = [{"url": mockup_url}]

            try:
                r = await client.post(
                    f"{PUBLER_BASE}/posts",
                    headers=headers,
                    json=payload,
                )
                if r.status_code in (200, 201):
                    results.append({"platform": p["key"], "status": "scheduled", "detail": r.json()})
                else:
                    results.append({"platform": p["key"], "status": "error", "detail": f"HTTP {r.status_code}: {r.text[:120]}"})
            except Exception as e:
                results.append({"platform": p["key"], "status": "error", "detail": str(e)[:120]})

    return results


def _save_report(data: dict) -> str:
    os.makedirs(MEDIA_BAY_DIR, exist_ok=True)

    latest_path = os.path.join(MEDIA_BAY_DIR, "latest_report.json")
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = os.path.join(MEDIA_BAY_DIR, f"content_{ts}.md")

    tiktok   = data.get("tiktok", {})
    instagram = data.get("instagram", {})

    scheduled_str = ""
    if data.get("publer_results"):
        rows = "\n".join(
            f"- {r['platform'].upper()}: {r['status'].upper()} — {r.get('detail', '')}"
            if isinstance(r.get("detail"), str) else
            f"- {r['platform'].upper()}: {r['status'].upper()}"
            for r in data["publer_results"]
        )
        scheduled_str = f"\n## Publer Schedule\n{rows}\n"

    md = f"""# Media Bay Report — {data['run_date']} UTC

**Product:** {data['product_title']} ({data['product_type']})
**Model:** {data['model_used']}
{"**Mockup:** " + data['mockup_url'] if data.get('mockup_url') else ""}

## TikTok / Reel

**Hook:** {tiktok.get('hook', '')}

{tiktok.get('caption', '')}

{' '.join(tiktok.get('hashtags', []))}

## Instagram

**Hook:** {instagram.get('hook', '')}

{instagram.get('caption', '')}

{' '.join(instagram.get('hashtags', []))}
{scheduled_str}"""

    with open(md_path, "w") as f:
        f.write(md)

    return md_path


def media_bay_midnight_report() -> dict:
    from datetime import timezone, timedelta
    cst = timezone(timedelta(hours=-6))
    today_start = datetime.now(cst).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_str = datetime.now(cst).strftime("%Y-%m-%d")

    content_count = 0
    products_covered = []

    if os.path.isdir(MEDIA_BAY_DIR):
        for fname in sorted(os.listdir(MEDIA_BAY_DIR)):
            if not fname.startswith("content_") or not fname.endswith(".md"):
                continue
            fpath = os.path.join(MEDIA_BAY_DIR, fname)
            if os.path.getmtime(fpath) < today_start:
                continue
            content_count += 1
            try:
                with open(fpath) as mf:
                    for line in mf:
                        if line.startswith("**Product:**"):
                            products_covered.append(line.replace("**Product:**", "").strip())
                            break
            except Exception:
                pass

    nothing = content_count == 0
    data = {
        "run_date":                today_str,
        "nothing_to_report":       nothing,
        "content_generated_today": content_count,
        "products_covered":        products_covered,
    }

    os.makedirs(MEDIA_BAY_DIR, exist_ok=True)
    with open(os.path.join(MEDIA_BAY_DIR, "latest_report.json"), "w") as f:
        json.dump(data, f, indent=2)

    return data


async def get_latest_report() -> dict | None:
    path = os.path.join(MEDIA_BAY_DIR, "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


async def run_media_bay(
    product_title: str,
    product_description: str,
    product_type: str = "T-Shirt",
    mockup_url: str = "",
    schedule_post: bool = False,
) -> dict:
    content, model = await _generate_content(
        product_title, product_description, product_type, mockup_url
    )

    publer_results: list[dict] = []
    if schedule_post:
        publer_results = await _schedule_publer(product_title, content, mockup_url)

    publer_scheduled = any(r["status"] == "scheduled" for r in publer_results)

    data = {
        "product_title":    product_title,
        "product_type":     product_type,
        "mockup_url":       mockup_url,
        "tiktok":           content["tiktok"],
        "instagram":        content["instagram"],
        "publer_scheduled": publer_scheduled,
        "publer_results":   publer_results,
        "model_used":       model,
        "run_date":         datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    }

    data["report_path"] = _save_report(data)
    return data
