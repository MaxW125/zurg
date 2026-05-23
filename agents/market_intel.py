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

# Static fallback — used if the dynamic query generation fails.
_ETSY_MARKET_QUERIES_FALLBACK = [
    ("funny graphic tee gift",          "Apparel"),
    ("hobby niche sweatshirt gift",     "Apparel"),
    ("funny coffee mug gift",           "Ceramic Mug"),
    ("novelty mug gift idea",           "Ceramic Mug"),
    ("canvas tote bag gift",            "Tote Bag"),
    ("book lover tote bag",             "Tote Bag"),
    ("funny tumbler gift",              "Tumbler"),
    ("novelty drinkware gift niche",    "Tumbler"),
    ("funny die cut sticker",           "Die-Cut Sticker"),
    ("cute niche laptop sticker",       "Die-Cut Sticker"),
    ("funny apron gift kitchen",        "Cotton Apron"),
    ("novelty cooking apron gift",      "Cotton Apron"),
    ("niche dad hat gift",              "Classic Dad Cap"),
    ("hobby baseball cap gift",         "Classic Dad Cap"),
]


async def _generate_search_queries() -> list[tuple[str, str]]:
    """Ask Haiku to generate fresh, seasonally-aware Etsy search terms each run.
    Falls back to the static list if the call fails or returns bad JSON."""
    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""Today is {today}. You are helping a print-on-demand Etsy store find trending niches.

Generate 2 Etsy search queries for EACH of these product types:
- Apparel (T-Shirt, Hoodie, Sweatshirt)
- Ceramic Mug
- Tote Bag
- Tumbler
- Die-Cut Sticker
- Cotton Apron
- Classic Dad Cap

Each query must be 3-6 words that would surface listings that are:
- Relevant to the current season or upcoming events (it's {today})
- Gift-purchase motivated (birthdays, holidays, "gift for X")
- Specific to a passionate niche community (dog moms, nurses, gamers, etc.)

Vary the niches across product types — don't repeat the same community twice.

Return ONLY a JSON array of 14 objects with "keyword" and "product_type" keys:
[{{"keyword": "funny dog mom shirt", "product_type": "Apparel"}}, ...]

Raw JSON only. No explanation."""

    try:
        import json
        from agents.llm_client import call_claude_haiku
        raw = await call_claude_haiku(prompt, room="market_intel")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        queries = [(item["keyword"], item["product_type"]) for item in data if "keyword" in item and "product_type" in item]
        if len(queries) >= 7:  # at least one per product type
            print(f"[market_intel] Generated {len(queries)} dynamic search queries")
            return queries
        print(f"[market_intel] Dynamic queries too few ({len(queries)}) — using fallback")
    except Exception as e:
        print(f"[market_intel] Dynamic query generation failed: {e} — using fallback")
    return _ETSY_MARKET_QUERIES_FALLBACK


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

def _fetch_etsy_market(queries: list[tuple[str, str]]) -> str:
    """Search public Etsy listings using the provided queries.
    Samples 6 from the list, collects all listings, aggregates by favorites,
    and returns a synthesised summary of trending tags and top listings."""
    api_key = os.getenv("ETSY_API_KEY", "")
    secret  = os.getenv("ETSY_SHARED_SECRET", "")
    if not api_key or not secret:
        return ""

    import random
    from collections import Counter
    queries = random.sample(queries, min(6, len(queries)))

    headers  = {"x-api-key": f"{api_key}:{secret}"}
    all_listings: list[dict] = []

    try:
        with httpx.Client(timeout=20) as client:
            for keyword, product_type in queries:
                r = client.get(
                    f"{ETSY_BASE}/application/listings/active",
                    headers=headers,
                    params={
                        "keywords":   keyword,
                        "sort_on":    "score",
                        "sort_order": "desc",
                        "limit":      15,
                    },
                )
                if r.status_code != 200:
                    print(f"[market_intel] Etsy search '{keyword}' status {r.status_code}")
                    continue
                for item in r.json().get("results", []):
                    item["_product_type"] = product_type
                    all_listings.append(item)
    except Exception as e:
        print(f"[market_intel] Etsy market fetch failed: {e}")
        return ""

    if not all_listings:
        return ""

    # Sort all collected listings by favorites descending
    all_listings.sort(key=lambda x: x.get("num_favorers", 0), reverse=True)
    top = all_listings[:30]

    # Rank product types by average favorites across their listings
    from collections import defaultdict
    pt_favs: dict = defaultdict(list)
    for item in all_listings:
        pt = item.get("_product_type", "Unknown")
        pt_favs[pt].append(item.get("num_favorers", 0))

    pt_ranked = sorted(
        [(pt, sum(favs) / len(favs), len(favs)) for pt, favs in pt_favs.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    ranking_lines = [
        f"  {i+1}. {pt} — avg {avg:.0f} favorites ({count} listings sampled)"
        for i, (pt, avg, count) in enumerate(pt_ranked)
    ]

    # Count tag frequency across top listings
    tag_counter: Counter = Counter()
    for item in top:
        for tag in (item.get("tags") or []):
            tag_counter[tag.lower()] += 1

    top_tags = tag_counter.most_common(15)
    tag_summary = ", ".join(f"{tag} ({n})" for tag, n in top_tags if n > 1)

    # Top 5 listing examples by favorites
    example_lines = []
    for item in all_listings[:5]:
        title   = (item.get("title") or "")[:70]
        fav     = item.get("num_favorers", 0)
        pt      = item.get("_product_type", "")
        tags    = (item.get("tags") or [])[:4]
        tag_str = ", ".join(tags)
        example_lines.append(f'- "{title}" — {fav} fav | {pt} | tags: {tag_str}')

    lines = [
        f"=== Etsy Market Intelligence ({len(all_listings)} listings across {len(queries)} product searches) ===",
        f"\nPRODUCT TYPE PERFORMANCE RANKING (by avg favorites — use this to pick product type):",
    ] + ranking_lines + [
        f"\nTop recurring tags (by frequency in high-favorites listings):",
        tag_summary or "— no repeated tags found",
        f"\nTop listings by favorites:",
    ] + example_lines

    return "\n".join(lines)


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


# ── Seasonal context ───────────────────────────────────────────

async def get_seasonal_context() -> str:
    """Ask Haiku what holidays or notable events are coming in the next 4 weeks.
    Returns a short plain-text summary, or "" if nothing notable or the call fails."""
    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""Today is {today}.

List any holidays, cultural events, or gifting moments happening NOW or within the NEXT 4 WEEKS that are relevant to print-on-demand or gift-buying (e.g. Mother's Day, graduation season, Pride Month, Halloween, Valentine's Day).

Rules:
- Only include events within 4 weeks of today. If an event is more than 4 weeks away, do not mention it.
- If there are genuinely no notable events in the next 4 weeks, say exactly: "No major gifting events in the next 4 weeks."
- Do not guess or invent events. Only include ones you are certain about.
- Be concise — one line per event, include how far away it is.

Output as a plain bulleted list."""

    try:
        from agents.llm_client import call_claude_haiku
        result = await call_claude_haiku(prompt, room="market_intel")
        # Discard if it looks like a hallucination or is suspiciously long
        if len(result) > 600:
            result = result[:600]
        return result.strip()
    except Exception as e:
        print(f"[market_intel] Seasonal context failed: {e}")
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
    queries = await _generate_search_queries()
    result = await loop.run_in_executor(None, _fetch_etsy_market, queries)
    if result:
        print("[market_intel] Using Etsy API data")
        return result

    print("[market_intel] Etsy API unavailable — falling back to DuckDuckGo")
    result = await loop.run_in_executor(None, _fetch_ddg)
    return result
