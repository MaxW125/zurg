import os
import asyncio
import base64
import httpx
from agents.printify_client import upload_image, create_product, get_mockup_urls, download_mockup, publish_product, get_product
from agents.product_catalog import get_blueprint
from agents.notify import notify

SHOPIFY_API_VERSION = "2025-01"


def _shopify_headers() -> dict:
    return {
        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
        "Content-Type": "application/json",
    }


def _shopify_url(path: str) -> str:
    store = os.getenv("SHOPIFY_STORE_URL", "")
    return f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/{path}"


async def _attach_image_to_shopify(image_path: str, product_id: int, client: httpx.AsyncClient) -> str:
    """Base64-encode a local image and attach it to a Shopify product. Returns image src URL."""
    disk_path = os.path.join("frontend", "public", image_path.lstrip("/"))
    with open(disk_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    filename = os.path.basename(disk_path)
    payload = {
        "image": {
            "attachment": image_data,
            "filename": filename,
            "alt": "Product design",
        }
    }
    r = await client.post(
        _shopify_url(f"products/{product_id}/images.json"),
        json=payload,
        headers=_shopify_headers(),
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["image"]["src"]


async def run_factory(input: dict) -> dict:
    """
    Publish an approved design to Shopify (via Printify) and Etsy.

    Pipeline:
      1. Upload flat design image to Printify (shared image_id across both shops)
      2. Create + publish Printify product to Shopify — Printify creates the Shopify
         listing and auto-syncs mockup images when they're generated (async on Printify's side)
      3. Create + publish Printify product to Etsy — same flow, Etsy OAuth required

    Input keys:
      - image_path: web path to the flat design (e.g. /assets/generated/foo.png)
      - niche, product_type, image_prompt, keywords, title, description, tags

    Returns:
      - product_id, product_url, storefront_url, title, model_used
    """
    niche        = input.get("niche", "Custom Design")
    product_type = input.get("product_type", "Unisex T-Shirt")
    image_path   = input.get("image_path", "")
    blueprint    = get_blueprint(product_type)
    _raw_color   = input.get("shirt_color", blueprint.get("preferred_color", "black")).lower()
    shirt_color  = _raw_color

    title       = input.get("title") or f"{niche} — {product_type}"
    description = input.get("description") or f"{niche} {product_type}"

    printify_token = os.getenv("PRINTIFY_API_TOKEN", "")
    etsy_shop_id   = os.getenv("PRINTIFY_ETSY_SHOP_ID", "")

    # Upload design image to Printify once — shared image_id for both shops
    image_id  = None
    disk_path = os.path.join("frontend", "public", image_path.lstrip("/"))

    if printify_token and image_path:
        try:
            filename = os.path.basename(disk_path)
            image_id = await upload_image(disk_path, filename)
        except Exception as e:
            print(f"[factory] Printify image upload failed: {e}")

    # ── Step 1: Etsy ─────────────────────────────────────────────────────────
    # Run Etsy first — Etsy IS connected so publish triggers mockup generation.
    # We download the mockup here and reuse it for the Shopify listing too,
    # since the Shopify Printify shop may be disconnected and can't generate its own.
    etsy_product_url = None
    etsy_printify_id = None
    mockup_path      = None   # will be reused by Shopify if found

    if image_id and etsy_shop_id:
        try:
            print(f"[factory] Creating Etsy product in Printify shop {etsy_shop_id}...")
            ep = await create_product(
                title=title,
                description=description,
                image_id=image_id,
                blueprint_id=blueprint["blueprint_id"],
                print_provider_id=blueprint["print_provider"],
                tags=input.get("tags") or input.get("keywords", []),
                preferred_color=shirt_color,
                shop_id=etsy_shop_id,
            )
            etsy_pid          = ep["id"]
            etsy_preferred    = ep.get("_preferred_variant_ids", [])
            print(f"[factory] Etsy product created: {etsy_pid} — publishing...")

            await publish_product(etsy_pid, shop_id=etsy_shop_id)
            print(f"[factory] Etsy publish sent — polling for mockups...")

            # Phase 1: poll up to 120s just for mockup images (needed for Shopify listing)
            etsy_mock_urls: list[str] = []
            for _ in range(40):
                await asyncio.sleep(3)
                prod   = await get_product(etsy_pid, shop_id=etsy_shop_id)
                images = prod.get("images", [])
                if images:
                    preferred_set = set(etsy_preferred)
                    if preferred_set:
                        etsy_mock_urls = [
                            img["src"] for img in images
                            if img.get("src") and preferred_set.intersection(img.get("variant_ids", []))
                        ]
                    etsy_mock_urls = etsy_mock_urls or [img["src"] for img in images if img.get("src")]
                    print(f"[factory] Etsy mockups ready: {len(etsy_mock_urls)}")
                    break

            # Phase 2: poll up to 30s for the Etsy listing URL
            etsy_url = None
            for _ in range(10):
                await asyncio.sleep(3)
                prod   = await get_product(etsy_pid, shop_id=etsy_shop_id)
                handle = (prod.get("external") or {}).get("handle") or ""
                if handle:
                    etsy_url = handle
                    print(f"[factory] Etsy listing live: {etsy_url}")
                    break

            # Printify sometimes shows "Publishing error" on first attempt but succeeds on retry
            if not etsy_url:
                print(f"[factory] Etsy URL not found — retrying publish...")
                await publish_product(etsy_pid, shop_id=etsy_shop_id)
                for _ in range(10):
                    await asyncio.sleep(3)
                    prod   = await get_product(etsy_pid, shop_id=etsy_shop_id)
                    handle = (prod.get("external") or {}).get("handle") or ""
                    if handle:
                        etsy_url = handle
                        print(f"[factory] Etsy listing live (retry): {etsy_url}")
                        break

            if etsy_mock_urls:
                flat_name   = os.path.splitext(os.path.basename(disk_path))[0]
                mockup_name = f"{flat_name}_mockup.png"
                mockup_disk = os.path.join(os.path.dirname(disk_path), mockup_name)
                await download_mockup(etsy_mock_urls[0], mockup_disk)
                mockup_path = f"/assets/generated/{mockup_name}"
                print(f"[factory] Mockup downloaded: {mockup_name}")
            else:
                print(f"[factory] No mockups from Etsy — using flat design")

            if not etsy_url:
                await notify(
                    "⚠️ Etsy publish failed for: " + title + "\n"
                    "Fix: printify.com → Stores → KrakenAndCoDesigns → reconnect Etsy"
                )
                etsy_url = "https://www.etsy.com/shop/KrakenAndCoDesigns"

            etsy_product_url = etsy_url
            etsy_printify_id = etsy_pid
        except Exception as e:
            import traceback
            print(f"[factory] Etsy flow failed: {e}")
            traceback.print_exc()
            await notify(
                "⚠️ Etsy publish error for: " + title + "\n"
                f"Error: {str(e)[:120]}\n"
                "Fix: printify.com → Stores → KrakenAndCoDesigns → reconnect Etsy"
            )
    elif not etsy_shop_id:
        print("[factory] Etsy skipped — PRINTIFY_ETSY_SHOP_ID not set")

    # ── Step 2: Shopify ───────────────────────────────────────────────────────
    # Use the mockup downloaded from Etsy. Also create a Printify product in the
    # Shopify shop so fulfillment works once the Shopify connection is restored.
    async def _shopify_flow() -> dict:
        if not image_id:
            raise RuntimeError("image_id required — Printify upload failed")

        # Create Shopify Printify product (for fulfillment when shop reconnects)
        sp = await create_product(
            title=title,
            description=description,
            image_id=image_id,
            blueprint_id=blueprint["blueprint_id"],
            print_provider_id=blueprint["print_provider"],
            tags=input.get("tags") or input.get("keywords", []),
            preferred_color=shirt_color,
        )
        pid = sp["id"]
        print(f"[factory] Shopify Printify product created: {pid}")

        try:
            await publish_product(pid)
        except Exception as e:
            print(f"[factory] Shopify publish failed (shop disconnected?): {e}")

        # Use Etsy mockup if we got one; otherwise fall back to flat design
        listing_image_path = mockup_path or image_path
        mockup_used        = bool(mockup_path)

        product_payload = {
            "product": {
                "title":        title,
                "body_html":    f"<p>{description}</p>",
                "product_type": product_type,
                "status":       "draft",
                "tags":         ", ".join(input.get("tags") or input.get("keywords", [])),
                "variants":     [{"price": "29.99", "requires_shipping": True, "taxable": True}],
            }
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _shopify_url("products.json"),
                json=product_payload,
                headers=_shopify_headers(),
            )
            r.raise_for_status()
            shopify_product = r.json()["product"]
            shopify_id      = shopify_product["id"]
            if listing_image_path:
                await _attach_image_to_shopify(listing_image_path, shopify_id, client)

        store = os.getenv("SHOPIFY_STORE_URL", "")
        return {
            "printify_product_id": pid,
            "product_id":          shopify_id,
            "product_url":         f"https://{store}/admin/products/{shopify_id}",
            "storefront_url":      f"https://{store}/products/{shopify_product['handle']}",
            "mockup_used":         mockup_used,
        }

    shopify_result = await _shopify_flow()

    await notify(f"✅ Shopify live: {title}\n{shopify_result['product_url']}")
    if etsy_product_url:
        await notify(f"✅ Etsy live: {title}\n{etsy_product_url}")

    return {
        "product_id":               shopify_result["product_id"],
        "product_url":              shopify_result["product_url"],
        "storefront_url":           shopify_result["storefront_url"],
        "title":                    title,
        "description":              description,
        "model_used":               "pre-approved",
        "printify_product_id":      shopify_result["printify_product_id"],
        "mockup_used":              shopify_result["mockup_used"],
        "etsy_product_url":         etsy_product_url,
        "etsy_printify_product_id": etsy_printify_id,
    }
