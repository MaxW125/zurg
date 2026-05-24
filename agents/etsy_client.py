"""
Direct Etsy API client for Zurg.

Bypasses the Printify-Etsy OAuth integration (which expires and requires manual
browser reconnection) by posting listings directly to Etsy's API.

Printify products are still created for fulfillment — this just handles listing
creation independently so we own the OAuth tokens and can auto-refresh them.

OAuth flow (one-time setup):
  1. Visit http://localhost:9000/auth/etsy in a browser
  2. Approve access on Etsy
  3. Tokens are saved to .env automatically

After setup, access tokens auto-refresh every hour. Refresh tokens never expire.
"""

import os
import time
import hashlib
import base64
import httpx
from pathlib import Path

ETSY_BASE  = "https://openapi.etsy.com/v3"
TOKEN_URL  = "https://api.etsy.com/v3/public/oauth/token"

ETSY_CLIENT_ID     = os.getenv("ETSY_API_KEY", "")
ETSY_SHARED_SECRET = os.getenv("ETSY_SHARED_SECRET", "")
ETSY_SHOP_ID       = os.getenv("ETSY_SHOP_ID", "")

# Cached per process to avoid hammering the API on every listing
_shipping_profiles:  list[dict] | None = None
_return_policy_id:   int | None = None

# Keywords to match shipping profile titles to product types
_PROFILE_KEYWORDS: dict[str, list[str]] = {
    "unisex t-shirt":      ["t-shirt", "t shirt", "tee"],
    "t-shirt":             ["t-shirt", "t shirt", "tee"],
    "long sleeve":         ["long-sleeve", "long sleeve"],
    "hoodie":              ["hoodie", "sweatshirt"],
    "crewneck sweatshirt": ["sweatshirt", "hoodie"],
    "ceramic mug":         ["mug"],
    "tote bag":            ["tote"],
    "tumbler":             ["tumbler", "drinkware", "mug"],
    "die-cut sticker":     ["sticker"],
    "classic dad cap":     ["hat", "cap", "accessories"],
    "cotton apron":        ["apron", "accessories"],
}

# Etsy taxonomy IDs per product type (affects browse category)
_TAXONOMY_IDS = {
    "unisex t-shirt":     68887447,
    "t-shirt":            68887447,
    "hoodie":             68887445,
    "hooded sweatshirt":  68887445,
    "crewneck sweatshirt":68887445,
    "long sleeve":        68887447,
    "ceramic mug":        5765,
    "tote bag":           68887455,
    "tumbler":            5765,       # drinkware category
    "die-cut sticker":    69150931,   # stickers & decals
    "classic dad cap":    68887444,   # hats & caps
    "cotton apron":       68887455,
}


def _taxonomy_id(product_type: str) -> int:
    return _TAXONOMY_IDS.get(product_type.lower(), 68887447)


# ── Token management ──────────────────────────────────────────────────────────

def _load_tokens() -> dict:
    return {
        "access_token":  os.getenv("ETSY_ACCESS_TOKEN", ""),
        "refresh_token": os.getenv("ETSY_REFRESH_TOKEN", ""),
        "expires_at":    float(os.getenv("ETSY_TOKEN_EXPIRES_AT", "0")),
    }


def save_tokens(access_token: str, refresh_token: str, expires_in: int) -> None:
    """Persist tokens to .env and update os.environ for the running process."""
    expires_at = time.time() + expires_in - 60  # 60s buffer before real expiry

    env_path = Path(".env")
    lines    = env_path.read_text().splitlines() if env_path.exists() else []

    keys_written = set()
    new_lines = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key == "ETSY_ACCESS_TOKEN":
            new_lines.append(f"ETSY_ACCESS_TOKEN={access_token}")
            keys_written.add(key)
        elif key == "ETSY_REFRESH_TOKEN":
            new_lines.append(f"ETSY_REFRESH_TOKEN={refresh_token}")
            keys_written.add(key)
        elif key == "ETSY_TOKEN_EXPIRES_AT":
            new_lines.append(f"ETSY_TOKEN_EXPIRES_AT={expires_at}")
            keys_written.add(key)
        else:
            new_lines.append(line)

    if "ETSY_ACCESS_TOKEN"    not in keys_written:
        new_lines.append(f"ETSY_ACCESS_TOKEN={access_token}")
    if "ETSY_REFRESH_TOKEN"   not in keys_written:
        new_lines.append(f"ETSY_REFRESH_TOKEN={refresh_token}")
    if "ETSY_TOKEN_EXPIRES_AT" not in keys_written:
        new_lines.append(f"ETSY_TOKEN_EXPIRES_AT={expires_at}")

    env_path.write_text("\n".join(new_lines) + "\n")

    os.environ["ETSY_ACCESS_TOKEN"]    = access_token
    os.environ["ETSY_REFRESH_TOKEN"]   = refresh_token
    os.environ["ETSY_TOKEN_EXPIRES_AT"] = str(expires_at)
    print(f"[etsy] Tokens saved — access token valid for {expires_in}s")


async def _refresh_access_token() -> str:
    refresh_token = os.getenv("ETSY_REFRESH_TOKEN", "")
    if not refresh_token:
        raise RuntimeError("Etsy not authorized — visit http://localhost:9000/auth/etsy to connect")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "client_id":     ETSY_CLIENT_ID,
                "refresh_token": refresh_token,
            },
        )
        r.raise_for_status()
        data = r.json()

    save_tokens(
        data["access_token"],
        data.get("refresh_token", refresh_token),  # Etsy may or may not rotate refresh token
        data["expires_in"],
    )
    return data["access_token"]


async def _get_token() -> str:
    """Return a valid access token, refreshing if expired."""
    tokens = _load_tokens()
    if tokens["access_token"] and time.time() < tokens["expires_at"]:
        return tokens["access_token"]
    print("[etsy] Access token expired — refreshing...")
    return await _refresh_access_token()


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "x-api-key":     f"{ETSY_CLIENT_ID}:{ETSY_SHARED_SECRET}",
        "Content-Type":  "application/json",
    }


# ── Shop profile helpers (cached) ─────────────────────────────────────────────

async def _get_shipping_profiles() -> list[dict]:
    global _shipping_profiles
    if _shipping_profiles is not None:
        return _shipping_profiles

    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/shipping-profiles",
            headers=_headers(token),
        )
        r.raise_for_status()
        _shipping_profiles = r.json().get("results", [])

    if not _shipping_profiles:
        raise RuntimeError("No shipping profiles in Etsy shop — create one at etsy.com/your/shops/me/shipping-settings")
    return _shipping_profiles


async def _get_shipping_profile_id(product_type: str = "") -> int:
    profiles = await _get_shipping_profiles()
    keywords = _PROFILE_KEYWORDS.get(product_type.lower(), [])
    for kw in keywords:
        for p in profiles:
            if kw in p.get("title", "").lower():
                print(f"[etsy] Shipping profile matched: {p['shipping_profile_id']} ({p['title']})")
                return p["shipping_profile_id"]
    # Fall back to first profile
    print(f"[etsy] No shipping profile match for '{product_type}' — using first: {profiles[0]['title']}")
    return profiles[0]["shipping_profile_id"]


async def _get_return_policy_id() -> int | None:
    global _return_policy_id
    if _return_policy_id:
        return _return_policy_id

    token = await _get_token()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/policies/return",
                headers=_headers(token),
            )
        if r.status_code == 404:
            print("[etsy] No return policy found — proceeding without one")
            return None
        r.raise_for_status()
        data     = r.json()
        policies = data.get("results", [data] if data.get("return_policy_id") else [])
        if policies:
            _return_policy_id = policies[0]["return_policy_id"]
            print(f"[etsy] Using return policy: {_return_policy_id}")
        return _return_policy_id
    except Exception as e:
        print(f"[etsy] Could not fetch return policy: {e} — proceeding without one")
        return None


# ── Listing creation ──────────────────────────────────────────────────────────

async def create_listing(
    title: str,
    description: str,
    tags: list[str],
    price: float,
    product_type: str,
    quantity: int = 999,
) -> dict:
    """
    Create an active Etsy listing directly via the Etsy API.
    Returns the full listing dict — use listing['listing_id'] and listing['url'].
    """
    token               = await _get_token()
    shipping_profile_id = await _get_shipping_profile_id(product_type)
    return_policy_id    = await _get_return_policy_id()

    # Etsy: max 13 tags, 20 chars each, title max 140 chars
    clean_tags = [t.strip()[:20] for t in tags[:13]]

    payload: dict = {
        "quantity":            quantity,
        "title":               title[:140],
        "description":         description,
        "price":               price,
        "who_made":            "i_did",
        "when_made":           "made_to_order",
        "taxonomy_id":         _taxonomy_id(product_type),
        "shipping_profile_id": shipping_profile_id,
        "tags":                clean_tags,
        "is_supply":           False,
        "type":                "physical",
        "state":               "active",
        "readiness_state_id":  1,
    }
    if return_policy_id:
        payload["return_policy_id"] = return_policy_id

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings",
            json=payload,
            headers=_headers(token),
        )
        if not r.is_success:
            raise RuntimeError(f"Etsy {r.status_code}: {r.text}")
        return r.json()


async def upload_listing_image(listing_id: int, image_disk_path: str, rank: int = 1) -> dict:
    """Upload a local image file to an Etsy listing."""
    token = await _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key":     f"{ETSY_CLIENT_ID}:{ETSY_SHARED_SECRET}",
    }
    filename = os.path.basename(image_disk_path)
    with open(image_disk_path, "rb") as f:
        image_bytes = f.read()

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}/images",
            headers=headers,
            files={"image": (filename, image_bytes, "image/png")},
            data={"rank": rank},
        )
        r.raise_for_status()
        return r.json()


def listing_url(listing_id: int) -> str:
    return f"https://www.etsy.com/listing/{listing_id}"


def is_configured() -> bool:
    """True if OAuth tokens are saved and Etsy direct publishing is ready."""
    return bool(os.getenv("ETSY_ACCESS_TOKEN") and os.getenv("ETSY_REFRESH_TOKEN"))


async def fetch_listings(state: str = "active", limit: int = 100) -> list[dict]:
    """Return shop listings (active / draft / expired / inactive)."""
    token = await _get_token()
    results = []
    offset = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            r = await client.get(
                f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings",
                params={"state": state, "limit": min(limit, 100), "offset": offset},
                headers=_headers(token),
            )
            r.raise_for_status()
            data = r.json()
            batch = data.get("results", [])
            results.extend(batch)
            if len(results) >= data.get("count", 0) or len(batch) < 100:
                break
            offset += len(batch)
    return results


async def update_listing_price(listing_id: int, price_usd: float) -> dict:
    """Update the price of an existing active Etsy listing."""
    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}",
            headers=_headers(token),
            json={"price": round(price_usd, 2)},
        )
        r.raise_for_status()
        return r.json()


async def fetch_receipts(limit: int = 250) -> list[dict]:
    """Return shop receipts (orders). Paid receipts have was_paid=True."""
    token = await _get_token()
    results = []
    offset = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            r = await client.get(
                f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/receipts",
                params={"limit": min(limit, 100), "offset": offset},
                headers=_headers(token),
            )
            r.raise_for_status()
            data = r.json()
            batch = data.get("results", [])
            results.extend(batch)
            if len(results) >= data.get("count", 0) or len(batch) < 100:
                break
            offset += len(batch)
    return results
