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
import asyncio
import hashlib
import base64
import httpx
from pathlib import Path

ETSY_BASE  = "https://openapi.etsy.com/v3"
TOKEN_URL  = "https://api.etsy.com/v3/public/oauth/token"

ETSY_CLIENT_ID          = os.getenv("ETSY_API_KEY", "")
ETSY_SHARED_SECRET      = os.getenv("ETSY_SHARED_SECRET", "")
ETSY_SHOP_ID            = os.getenv("ETSY_SHOP_ID", "")
ETSY_PRODUCTION_PARTNER_ID = int(os.getenv("ETSY_PRODUCTION_PARTNER_ID", "0")) or None

# Return policy is stable — cache it. Shipping profiles are NOT cached so a newly
# created free-shipping profile is always picked up without needing a server restart.
_return_policy_id: int | None = None

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

# Shop section IDs — map product type to Etsy shop section
_SHOP_SECTIONS: dict[str, int] = {
    "unisex t-shirt":      58696947,  # Apparel
    "t-shirt":             58696947,
    "long sleeve":         58696947,
    "long sleeve t-shirt": 58696947,
    "hoodie":              58696947,
    "hooded sweatshirt":   58696947,
    "crewneck sweatshirt": 58696947,
    "classic dad cap":     58696947,
    "cotton apron":        58696947,
    "ceramic mug":         58697807,  # Mugs & Drinkware
    "tumbler":             58697807,
    "tote bag":            58697811,  # Accessories
    "die-cut sticker":     58696943,  # Stickers
}


# Materials per product type (up to 5 shown on Etsy listing)
_MATERIALS: dict[str, list[str]] = {
    "unisex t-shirt":      ["Cotton"],
    "t-shirt":             ["Cotton"],
    "long sleeve":         ["Cotton"],
    "long sleeve t-shirt": ["Cotton"],
    "hoodie":              ["Cotton", "Polyester"],
    "hooded sweatshirt":   ["Cotton", "Polyester"],
    "crewneck sweatshirt": ["Cotton", "Polyester"],
    "ceramic mug":         ["Ceramic"],
    "tote bag":            ["Cotton", "Canvas"],
    "tumbler":             ["Stainless Steel"],
    "die-cut sticker":     ["Vinyl"],
    "classic dad cap":     ["Cotton", "Polyester", "Spandex"],
    "cotton apron":        ["Cotton", "Polyester"],
}


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
    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/shipping-profiles",
            headers=_headers(token),
        )
        r.raise_for_status()
        profiles = r.json().get("results", [])

    if not profiles:
        raise RuntimeError("No shipping profiles in Etsy shop — create one at etsy.com/your/shops/me/shipping-settings")
    return profiles


async def _get_shipping_profile_id(product_type: str = "") -> int:
    profiles = await _get_shipping_profiles()
    # Always prefer a free shipping profile if one exists
    for p in profiles:
        if "free" in p.get("title", "").lower():
            print(f"[etsy] Using free shipping profile: {p['shipping_profile_id']}")
            return p["shipping_profile_id"]
    # Fall back to keyword match
    keywords = _PROFILE_KEYWORDS.get(product_type.lower(), [])
    for kw in keywords:
        for p in profiles:
            if kw in p.get("title", "").lower():
                print(f"[etsy] Shipping profile matched: {p['shipping_profile_id']} ({p['title']})")
                return p["shipping_profile_id"]
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
        "shipping_profile_id": shipping_profile_id,
        "tags":                clean_tags,
        "is_supply":           False,
        "type":                "physical",
        "state":               "active",
    }
    if ETSY_PRODUCTION_PARTNER_ID:
        payload["production_partner_ids"] = [ETSY_PRODUCTION_PARTNER_ID]
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


async def fetch_listing_images(listing_id: int) -> list[dict]:
    """Return existing images on an Etsy listing with their listing_image_ids."""
    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        # GET endpoint has no /shops/{shop_id}/ — only POST/DELETE do.
        r = await client.get(
            f"{ETSY_BASE}/application/listings/{listing_id}/images",
            headers=_headers(token),
        )
        r.raise_for_status()
        return r.json().get("results", [])


async def delete_listing_image(listing_id: int, listing_image_id: int) -> None:
    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.delete(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}/images/{listing_image_id}",
            headers=_headers(token),
        )
        if not r.is_success:
            raise RuntimeError(f"Etsy image delete {r.status_code}: {r.text}")


async def replace_listing_images(listing_id: int, image_urls: list[str]) -> dict[str, int]:
    """Upload a curated set of images to an Etsy listing, replacing all existing ones.

    Upload-first order: new images go up first so the listing always has ≥1 image,
    then old images are deleted. Avoids the Etsy '≥1 image required' 400 error.

    Returns {url: listing_image_id} for each successfully uploaded image.
    """
    old_ids = [img["listing_image_id"] for img in await fetch_listing_images(listing_id)]

    token = await _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key":     f"{ETSY_CLIENT_ID}:{ETSY_SHARED_SECRET}",
    }
    # Step 1 — upload new images (track rank order — Etsy's upload response sometimes
    # returns the same listing_image_id for every call, so we resolve IDs afterward by rank)
    uploaded_count = 0
    for rank, url in enumerate(image_urls, start=1):
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                r = await client.get(url)
                r.raise_for_status()
                image_bytes = r.content
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}/images",
                    headers=headers,
                    files={"image": (f"mockup_{rank}.jpg", image_bytes, "image/jpeg")},
                    data={"rank": rank},
                )
                if not r.is_success:
                    print(f"[etsy] Image upload failed rank {rank}: {r.status_code}: {r.text}")
                else:
                    uploaded_count += 1
                    print(f"[etsy] Uploaded image rank {rank}/{len(image_urls)}")
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[etsy] Image upload error rank {rank}: {e}")

    # Step 2 — delete original images now that new ones exist
    for img_id in old_ids:
        try:
            await delete_listing_image(listing_id, img_id)
        except Exception as e:
            print(f"[etsy] Could not delete old image {img_id}: {e}")

    # Step 3 — fetch the authoritative listing_image_ids from Etsy by rank
    # (upload response can return the same ID for every upload — this is the reliable path)
    url_to_image_id: dict[str, int] = {}
    try:
        final_images = await fetch_listing_images(listing_id)
        final_images.sort(key=lambda x: x.get("rank", 99))
        for i, url in enumerate(image_urls):
            if i < len(final_images):
                url_to_image_id[url] = final_images[i]["listing_image_id"]
    except Exception as e:
        print(f"[etsy] Could not resolve final image IDs (variation linking will be skipped): {e}")

    return url_to_image_id


async def get_listing_color_property(listing_id: int) -> tuple[int, dict[str, int]]:
    """Fetch the color property_id and {lowercase_color_name: value_id} for a listing.

    Used to link uploaded images to color variation values via set_variation_images().
    Returns (0, {}) if the listing has no color property (e.g. stickers, which vary by size).
    """
    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{ETSY_BASE}/application/listings/{listing_id}/inventory",
            headers=_headers(token),
        )
        r.raise_for_status()
    color_property_id = 0
    color_value_map: dict[str, int] = {}
    for product in r.json().get("products", []):
        for pv in product.get("property_values", []):
            if "color" in pv.get("property_name", "").lower():
                color_property_id = pv["property_id"]
                for name, vid in zip(pv.get("values", []), pv.get("value_ids", [])):
                    color_value_map.setdefault(name.lower(), vid)
    return color_property_id, color_value_map


async def set_variation_images(listing_id: int, variation_images: list[dict]) -> None:
    """Link listing images to color variation values.

    variation_images: [{"property_id": int, "value_id": int, "image_id": int}]
    Replaces ALL variation-image associations for the listing — must include every
    color you want linked, not just new ones.
    """
    if not variation_images:
        return
    token = await _get_token()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}/variation-images",
            headers=_headers(token),
            json={"variation_images": variation_images},
        )
        if not r.is_success:
            print(f"[etsy] set_variation_images {r.status_code}: {r.text}")


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


async def update_listing(
    listing_id: int,
    product_type: str = "",
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """
    Patch an Etsy listing after Printify publishes it.
    Sets all fields Printify doesn't control: category, shipping, return policy,
    production partner, who_made, when_made.
    """
    token               = await _get_token()
    shipping_profile_id = await _get_shipping_profile_id(product_type)
    return_policy_id    = await _get_return_policy_id()

    payload: dict = {
        "shipping_profile_id": shipping_profile_id,
        "who_made":            "i_did",
        "when_made":           "made_to_order",
        "type":                "physical",
        "is_supply":           False,
        "materials":           _MATERIALS.get(product_type.lower(), []),
    }
    section_id = _SHOP_SECTIONS.get(product_type.lower())
    if section_id:
        payload["shop_section_id"] = section_id
    if title:
        payload["title"] = title[:140]
    if description:
        payload["description"] = description
    if tags:
        payload["tags"] = [t.strip()[:20] for t in tags[:13]]
    if ETSY_PRODUCTION_PARTNER_ID:
        payload["production_partner_ids"] = [ETSY_PRODUCTION_PARTNER_ID]
    if return_policy_id:
        payload["return_policy_id"] = return_policy_id

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.patch(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}",
            json=payload,
            headers=_headers(token),
        )
        if not r.is_success:
            raise RuntimeError(f"Etsy update {r.status_code}: {r.text}")
        return r.json()


async def set_listing_flags(
    listing_id: int,
    featured: bool | None = None,
    auto_renew: bool | None = None,
) -> dict:
    """
    Toggle featured status and/or auto-renewal on an existing listing.
    Called by Pricing Room / Shop Health agent for top performers — not by the factory.
    Pass only the flags you want to change; omit the rest.
    """
    payload = {}
    if featured is not None:
        payload["featured_rank"] = 1 if featured else -1
    if auto_renew is not None:
        payload["should_auto_renew"] = auto_renew
    if not payload:
        return {}

    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            f"{ETSY_BASE}/application/shops/{ETSY_SHOP_ID}/listings/{listing_id}",
            json=payload,
            headers=_headers(token),
        )
        if not r.is_success:
            raise RuntimeError(f"Etsy flag update {r.status_code}: {r.text}")
        return r.json()


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
