"""
Printify API client for Zurg.

Handles:
  - Blueprint/variant lookup
  - Design image upload
  - Product creation (triggers mockup generation)
  - Mockup image polling + download
  - Shopify publish (optional — only if using Printify as fulfillment backend)

The API itself is FREE. Cost only applies when orders are fulfilled.

Env vars required:
  PRINTIFY_API_TOKEN   — from printify.com → Account → Connections
  PRINTIFY_SHOP_ID     — numeric ID from printify.com dashboard URL

Printify API docs: https://developers.printify.com/
"""

import os
import asyncio
import base64
import httpx

PRINTIFY_BASE = "https://api.printify.com/v1"

# Default blueprint/print provider for a basic unisex t-shirt.
# Blueprint 6 = Bella+Canvas 3001 Unisex Jersey Short Sleeve Tee
# Print provider 29 = Printify's own Monster Digital (reliable, US-based)
# These are reasonable defaults — override via env vars to switch products.
DEFAULT_BLUEPRINT_ID  = int(os.getenv("PRINTIFY_BLUEPRINT_ID",  "6"))
DEFAULT_PRINT_PROVIDER = int(os.getenv("PRINTIFY_PRINT_PROVIDER", "29"))


def _headers() -> dict:
    token = os.getenv("PRINTIFY_API_TOKEN", "")
    if not token:
        raise RuntimeError("PRINTIFY_API_TOKEN not set")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _shop_id() -> str:
    shop_id = os.getenv("PRINTIFY_SHOP_ID", "")
    if not shop_id:
        raise RuntimeError("PRINTIFY_SHOP_ID not set")
    return shop_id


async def upload_image(image_path: str, filename: str) -> str:
    """
    Upload a design image to Printify's media library.

    image_path: filesystem path to the PNG (e.g. frontend/public/assets/generated/foo.png)
    filename:   what to call it in Printify

    Returns the Printify image ID.
    """
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "file_name": filename,
        "contents": image_b64,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{PRINTIFY_BASE}/uploads/images.json",
            json=payload,
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()["id"]


async def get_variants(blueprint_id: int, print_provider_id: int) -> list[dict]:
    """
    Fetch available variants (sizes/colors) for a blueprint + provider combo.
    Returns the full variant list — caller picks which to include.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{PRINTIFY_BASE}/catalog/blueprints/{blueprint_id}/print_providers/{print_provider_id}/variants.json",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json().get("variants", [])


async def create_product(
    title: str,
    description: str,
    image_id: str,
    blueprint_id: int = DEFAULT_BLUEPRINT_ID,
    print_provider_id: int = DEFAULT_PRINT_PROVIDER,
    tags: list[str] | None = None,
    preferred_color: str = "black",
    shop_id: str | None = None,
) -> dict:
    """
    Create a product on Printify with the uploaded design image.

    Uses a standard front-print placement for t-shirts.
    Enables all available variants (sizes S-3XL) at a fixed price.

    Returns the full Printify product object (includes product ID).
    """
    variants = await get_variants(blueprint_id, print_provider_id)
    if not variants:
        raise RuntimeError(f"No variants found for blueprint {blueprint_id} / provider {print_provider_id}")

    # Variants come back grouped by color (e.g. all "Carolina Blue / S/M/L..." first).
    # Taking the first 50 naively risks excluding the preferred color entirely.
    # Fix: group by color, put the preferred color first, then fill to 50.
    from collections import defaultdict
    color_groups: dict[str, list] = defaultdict(list)
    for v in variants:
        vtitle = v.get("title", "")
        color_key = vtitle.split(" / ")[0].strip().lower() if " / " in vtitle else vtitle.lower()
        color_groups[color_key].append(v)

    preferred_key = preferred_color.lower()
    enabled: list = list(color_groups.get(preferred_key, []))
    for key, group in color_groups.items():
        if key != preferred_key:
            enabled.extend(group)
            if len(enabled) >= 100:
                break
    variants = enabled[:100]

    # Preferred color IDs are the ones we just prioritised — guaranteed in enabled set
    preferred_variant_ids = [v["id"] for v in color_groups.get(preferred_key, [])]
    print(f"[PRINTIFY] preferred_color={preferred_color!r}, {len(preferred_variant_ids)} variants in enabled set of {len(variants)}")

    variant_list = [
        {
            "id": v["id"],
            "price": 2999,  # $29.99 in cents
            "is_enabled": True,
        }
        for v in variants
    ]

    payload = {
        "title": title,
        "description": description,
        "blueprint_id": blueprint_id,
        "print_provider_id": print_provider_id,
        "variants": variant_list,
        "print_areas": [
            {
                "variant_ids": [v["id"] for v in variants],
                "placeholders": [
                    {
                        "position": "front",
                        "images": [
                            {
                                "id": image_id,
                                "x": 0.5,
                                "y": 0.5,
                                "scale": 1.0,
                                "angle": 0,
                            }
                        ],
                    }
                ],
            }
        ],
        "tags": tags or [],
    }

    sid = shop_id or _shop_id()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{PRINTIFY_BASE}/shops/{sid}/products.json",
            json=payload,
            headers=_headers(),
        )
        r.raise_for_status()
        product = r.json()
        product["_preferred_variant_ids"] = preferred_variant_ids
        return product


async def get_mockup_urls(
    printify_product_id: str,
    max_wait: int = 120,
    preferred_variant_ids: list[int] | None = None,
    shop_id: str | None = None,
) -> list[str]:
    """
    Poll a Printify product until mockup images are generated, then return their URLs.

    Mockup generation is async on Printify's side — usually takes 5-20 seconds.
    Polls every 3 seconds up to max_wait seconds before giving up.

    If preferred_variant_ids is provided, returns URLs for mockups that cover those
    variants first (e.g. black shirt mockups before other colors).
    """
    deadline = asyncio.get_event_loop().time() + max_wait
    preferred_set = set(preferred_variant_ids or [])
    sid = shop_id or _shop_id()

    async with httpx.AsyncClient(timeout=30) as client:
        while asyncio.get_event_loop().time() < deadline:
            r = await client.get(
                f"{PRINTIFY_BASE}/shops/{sid}/products/{printify_product_id}.json",
                headers=_headers(),
            )
            r.raise_for_status()
            images = r.json().get("images", [])
            print(f"[PRINTIFY] poll: {len(images)} images, preferred_set size={len(preferred_set)}")
            if not images:
                await asyncio.sleep(3)
                continue

            if preferred_set:
                preferred = [
                    img["src"] for img in images
                    if img.get("src") and preferred_set.intersection(img.get("variant_ids", []))
                ]
                print(f"[PRINTIFY] preferred color matches: {len(preferred)}")
                if preferred:
                    return preferred
                # No preferred color match — fall back to all images
                print(f"[PRINTIFY] no preferred match, returning all {len(images)} images")

            return [img["src"] for img in images if img.get("src")]

    return []


async def download_mockup(url: str, save_path: str) -> None:
    """Download a Printify CDN mockup image to a local file path."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(r.content)


async def publish_product(printify_product_id: str, shop_id: str | None = None) -> dict:
    """
    Publish a Printify product to its connected sales channel (Shopify or Etsy).
    Works for any Printify shop — pass shop_id to target a specific channel.
    """
    payload = {
        "title":       True,
        "description": True,
        "images":      True,
        "variants":    True,
        "tags":        True,
    }
    sid = shop_id or _shop_id()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{PRINTIFY_BASE}/shops/{sid}/products/{printify_product_id}/publish.json",
            json=payload,
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


async def get_product(printify_product_id: str, shop_id: str | None = None) -> dict:
    """Fetch a Printify product — used after publishing to retrieve the external listing URL."""
    sid = shop_id or _shop_id()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{PRINTIFY_BASE}/shops/{sid}/products/{printify_product_id}.json",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


async def publish_to_shopify(printify_product_id: str) -> dict:
    """
    Publish a Printify product to the connected Shopify store.

    Publishes with title, description, images, and variants visible.
    Returns the publish response.
    """
    payload = {
        "title":       True,
        "description": True,
        "images":      True,
        "variants":    True,
        "tags":        True,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{PRINTIFY_BASE}/shops/{_shop_id()}/products/{printify_product_id}/publish.json",
            json=payload,
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()
