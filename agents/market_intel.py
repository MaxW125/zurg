"""
Market intelligence gathering for the Researcher agent.

Priority:
  1. Everbee API — real Etsy bestseller data with revenue/sales estimates
  2. Etsy API    — live public listing data: titles, tags, views, favorites
  3. DuckDuckGo  — web search snippets (free, no API key)
Silent fail: if all three fail, returns "" and researcher uses LLM-only mode.
"""

import asyncio
import os
import httpx
from datetime import datetime


EVERBEE_BASE = "https://research-open-api.everbee.com"
ETSY_BASE    = "https://openapi.etsy.com/v3"

DDG_QUERIES = [
    f"best selling etsy graphic tee niches {datetime.now().strftime('%B %Y')}",
    f"trending t-shirt designs that sell {datetime.now().strftime('%Y')} hobbies animals humor",
    "most profitable print on demand shirt themes passionate communities",
]

# Keyword sets that surface different niche types on Etsy
_ETSY_MARKET_QUERIES = [
    ("funny animal shirt",       "Animals & Pets"),
    ("hobby enthusiast tee",     "Hobby Niches"),
    ("funny profession shirt",   "Jobs & Careers"),
    ("outdoor adventure tshirt", "Outdoor/Nature"),
    ("niche graphic tee gift",   "Gift Niches"),
]


# ── Everbee ────────────────────────────────────────────────────

def _fetch_everbee() -> str:
    """Fetch bestselling Etsy listings and trending keywords from Everbee API."""
    client_id = os.getenv("EVERBEE_CLIENT_ID", "")
    client_secret = os.getenv("EVERBEE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return ""

    headers = {
        "client_id": client_id,
        "client_secret": client_secret,
        "Content-Type": "application/json",
    }

    lines = ["=== Everbee Market Intelligence (Real Etsy Data) ==="]

    try:
        with httpx.Client(timeout=15) as client:
            # Top earning apparel listings
            r = client.get(
                f"{EVERBEE_BASE}/api/v1/listings",
                headers=headers,
                params={
                    "category_include": "clothing",
                    "sort_by": "est_mo_revenue",
                    "sort_order": "desc",
                    "limit": 20,
                },
            )
            if r.status_code == 200:
                data = r.json()
                listings = data.get("listings") or data.get("data") or []
                if listings:
                    lines.append("\n-- Top Earning Etsy Apparel Listings --")
                    for item in listings[:15]:
                        title = item.get("title", "")
                        revenue = item.get("est_mo_revenue", 0)
                        sales = item.get("est_mo_sales", 0)
                        tags = item.get("tags", [])
                        if title:
                            tag_str = ", ".join(tags[:6]) if tags else ""
                            lines.append(
                                f"- \"{title[:80]}\" | ~${revenue}/mo, ~{sales} sales/mo"
                                + (f" | tags: {tag_str}" if tag_str else "")
                            )
            else:
                print(f"[market_intel] Everbee listings status: {r.status_code} — {r.text[:200]}")

            # Trending high-opportunity keywords
            r2 = client.get(
                f"{EVERBEE_BASE}/api/v1/keywords",
                headers=headers,
                params={
                    "category": "clothing",
                    "sort_by": "score",
                    "sort_order": "desc",
                    "limit": 20,
                },
            )
            if r2.status_code == 200:
                kdata = r2.json()
                keywords = kdata.get("keywords") or kdata.get("data") or []
                if keywords:
                    lines.append("\n-- High-Opportunity Etsy Keywords --")
                    for kw in keywords[:15]:
                        word = kw.get("keyword") or kw.get("term", "")
                        vol = kw.get("vol") or kw.get("volume", 0)
                        competition = kw.get("competition", "")
                        score = kw.get("score", 0)
                        if word:
                            lines.append(f"- \"{word}\" | vol: {vol}, competition: {competition}, score: {score}")
            else:
                print(f"[market_intel] Everbee keywords status: {r2.status_code} — {r2.text[:200]}")

    except Exception as e:
        print(f"[market_intel] Everbee fetch failed: {e}")
        return ""

    return "\n".join(lines) if len(lines) > 1 else ""


# ── Etsy API ──────────────────────────────────────────────────

def _fetch_etsy_market() -> str:
    """Search public Etsy listings for trending apparel niches using the Etsy API."""
    api_key = os.getenv("ETSY_API_KEY", "")
    secret  = os.getenv("ETSY_SHARED_SECRET", "")
    if not api_key or not secret:
        return ""

    headers = {"x-api-key": f"{api_key}:{secret}"}
    lines   = ["=== Etsy Market Intelligence (Live Listing Data) ==="]

    try:
        with httpx.Client(timeout=20) as client:
            for keyword, category in _ETSY_MARKET_QUERIES:
                r = client.get(
                    f"{ETSY_BASE}/application/listings/active",
                    headers=headers,
                    params={
                        "keywords":   keyword,
                        "sort_on":    "score",
                        "sort_order": "desc",
                        "limit":      10,
                    },
                )
                if r.status_code != 200:
                    print(f"[market_intel] Etsy search '{keyword}' status {r.status_code}")
                    continue
                results = r.json().get("results", [])
                if not results:
                    continue
                lines.append(f"\n-- {category} (search: \"{keyword}\") --")
                for item in results[:8]:
                    title = (item.get("title") or "")[:80]
                    views = item.get("views", 0)
                    fav   = item.get("num_favorers", 0)
                    tags  = (item.get("tags") or [])[:6]
                    price = item.get("price") or {}
                    amt   = price.get("amount", 0)
                    div   = price.get("divisor", 100) or 100
                    price_val = amt / div
                    tag_str = ", ".join(tags)
                    if title:
                        lines.append(
                            f"- \"{title}\" | views:{views}, fav:{fav}, ${price_val:.2f}"
                            + (f" | tags: {tag_str}" if tag_str else "")
                        )
    except Exception as e:
        print(f"[market_intel] Etsy market fetch failed: {e}")
        return ""

    return "\n".join(lines) if len(lines) > 1 else ""


# ── DuckDuckGo fallback ────────────────────────────────────────

def _fetch_ddg() -> str:
    """DuckDuckGo search fallback. Runs in executor to avoid blocking event loop."""
    try:
        from ddgs import DDGS
        client = DDGS()
        lines = ["=== Live Market Research (DuckDuckGo) ==="]
        for query in DDG_QUERIES:
            results = client.text(query, max_results=2)
            for r in results or []:
                snippet = r.get("body", "").strip()
                if snippet:
                    lines.append(f"- {snippet[:350]}")
        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception as e:
        print(f"[market_intel] DDG search failed: {e}")
        return ""


# ── Public API ─────────────────────────────────────────────────

async def gather_trends() -> str:
    """
    Fetch live market intelligence.
    Priority: Everbee (revenue data) → Etsy API (live listings) → DuckDuckGo (web).
    Returns "" if all three fail — researcher continues in LLM-only mode.
    """
    loop = asyncio.get_event_loop()

    result = await loop.run_in_executor(None, _fetch_everbee)
    if result:
        print("[market_intel] Using Everbee data")
        return result

    print("[market_intel] Everbee unavailable — trying Etsy API")
    result = await loop.run_in_executor(None, _fetch_etsy_market)
    if result:
        print("[market_intel] Using Etsy API data")
        return result

    print("[market_intel] Etsy API unavailable — falling back to DuckDuckGo")
    result = await loop.run_in_executor(None, _fetch_ddg)
    return result
