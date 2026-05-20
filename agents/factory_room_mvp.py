import os
import asyncio
import base64
import httpx
from agents.llm_client import call_local, call_claude_haiku
from agents.printify_client import upload_image, create_product, get_mockup_urls, download_mockup, publish_product, get_product
from agents.product_catalog import get_blueprint
from agents.notify import notify
from agents.brain import load_system_prompt

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
SHOPIFY_API_VERSION = "2025-01"

_DESCRIPTION_FALLBACK = """You are a Shopify product copywriter for a print-on-demand store.
Write a short, compelling product description (2-3 sentences max).
Focus on the niche audience and what makes the design special.
No fluff. Output only the description text."""


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
    Publish an approved design to Shopify.

    Pipeline:
      1. Write product description (Ollama → Claude fallback)
      2. Upload flat design to Printify → create product → wait for mockup
      3. Download mockup image, save alongside the flat design
      4. Create Shopify draft listing with the mockup image
         (falls back to flat design if Printify mockup generation fails)

    Input keys:
      - image_path: web path to the flat design (e.g. /assets/generated/foo.png)
      - niche, product_type, image_prompt, keywords

    Returns:
      - product_id, product_url, storefront_url, title, model_used
    """
    niche        = input.get("niche", "Custom Design")
    product_type = input.get("product_type", "Unisex T-Shirt")
    image_path   = input.get("image_path", "")
    blueprint    = get_blueprint(product_type)
    # Use preferred color from catalog; caller can override via shirt_color input
    _raw_color   = input.get("shirt_color", blueprint.get("preferred_color", "black")).lower()
    shirt_color  = _raw_color

    # Step 1 — write product description
    desc_prompt = f"""Write a product description for a {product_type} in the "{niche}" niche.
Design: {input.get('image_prompt', input.get('design_direction', ''))}"""

    description_system = load_system_prompt("factory", "factory", _DESCRIPTION_FALLBACK)
    model_used = "ollama"
    try:
        description = await call_local(desc_prompt, system=description_system)
    except Exception:
        model_used = "claude"
        description = await call_claude_haiku(desc_prompt, system=description_system, room="factory")

    title = f"{niche} — {product_type}"

    printify_token   = os.getenv("PRINTIFY_API_TOKEN", "")
    etsy_shop_id     = os.getenv("PRINTIFY_ETSY_SHOP_ID", "")

    # Step 2 — upload design image to Printify once (shared across both shops)
    image_id         = None
    listing_image_path = image_path
    disk_path        = os.path.join("frontend", "public", image_path.lstrip("/"))

    if printify_token and image_path:
        try:
            filename = os.path.basename(disk_path)
            image_id = await upload_image(disk_path, filename)
        except Exception as e:
            print(f"[factory] Printify image upload failed: {e}")

    # Step 3 — run Shopify and Etsy publish flows in parallel
    async def _shopify_flow() -> dict:
        result = {
            "printify_product_id": None,
            "listing_image_path":  image_path,
            "product_url":         None,
            "storefront_url":      None,
            "mockup_used":         False,
        }
        if image_id:
            try:
                printify_product      = await create_product(
                    title=title,
                    description=description,
                    image_id=image_id,
                    blueprint_id=blueprint["blueprint_id"],
                    print_provider_id=blueprint["print_provider"],
                    tags=input.get("keywords", []),
                    preferred_color=shirt_color,
                )
                pid                   = printify_product["id"]
                preferred_variant_ids = printify_product.get("_preferred_variant_ids", [])
                mockup_urls           = await get_mockup_urls(pid, preferred_variant_ids=preferred_variant_ids)
                if mockup_urls:
                    flat_name   = os.path.splitext(os.path.basename(disk_path))[0]
                    mockup_name = f"{flat_name}_mockup.png"
                    mockup_disk = os.path.join(os.path.dirname(disk_path), mockup_name)
                    await download_mockup(mockup_urls[0], mockup_disk)
                    result["listing_image_path"] = f"/assets/generated/{mockup_name}"
                    result["mockup_used"]        = True
                result["printify_product_id"] = pid
            except Exception as e:
                import traceback
                print(f"[factory] Printify mockup failed, using flat design: {e}")
                traceback.print_exc()

        product_payload = {
            "product": {
                "title":        title,
                "body_html":    f"<p>{description}</p>",
                "product_type": product_type,
                "status":       "draft",
                "tags":         ", ".join(input.get("keywords", [])),
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
            if result["listing_image_path"]:
                await _attach_image_to_shopify(result["listing_image_path"], shopify_id, client)

        store = os.getenv("SHOPIFY_STORE_URL", "")
        result["product_id"]    = shopify_id
        result["product_url"]   = f"https://{store}/admin/products/{shopify_id}"
        result["storefront_url"] = f"https://{store}/products/{shopify_product['handle']}"
        return result

    async def _etsy_flow() -> dict | None:
        if not image_id or not etsy_shop_id:
            return None
        try:
            printify_product = await create_product(
                title=title,
                description=description,
                image_id=image_id,
                blueprint_id=blueprint["blueprint_id"],
                print_provider_id=blueprint["print_provider"],
                tags=input.get("keywords", []),
                preferred_color=shirt_color,
                shop_id=etsy_shop_id,
            )
            pid = printify_product["id"]
            await publish_product(pid, shop_id=etsy_shop_id)
            # Fetch the published product to extract the Etsy listing URL
            published = await get_product(pid, shop_id=etsy_shop_id)
            external  = published.get("external") or {}
            etsy_url  = external.get("handle") or f"https://www.etsy.com/shop/KrakenAndCo"
            return {"etsy_printify_product_id": pid, "etsy_product_url": etsy_url}
        except Exception as e:
            import traceback
            print(f"[factory] Etsy publish failed (non-blocking): {e}")
            traceback.print_exc()
            return None

    shopify_result, etsy_result = await asyncio.gather(
        _shopify_flow(),
        _etsy_flow(),
        return_exceptions=True,
    )

    # Shopify is required — propagate any exception
    if isinstance(shopify_result, Exception):
        raise shopify_result

    etsy_product_url = None
    etsy_printify_id = None
    if isinstance(etsy_result, dict) and etsy_result:
        etsy_product_url = etsy_result.get("etsy_product_url")
        etsy_printify_id = etsy_result.get("etsy_printify_product_id")

    notify_lines = [f"✅ Published: {title}", f"Shopify: {shopify_result['product_url']}"]
    if etsy_product_url:
        notify_lines.append(f"Etsy: {etsy_product_url}")
    await notify("\n".join(notify_lines))

    return {
        "product_id":               shopify_result["product_id"],
        "product_url":              shopify_result["product_url"],
        "storefront_url":           shopify_result["storefront_url"],
        "title":                    title,
        "description":              description,
        "model_used":               model_used,
        "printify_product_id":      shopify_result["printify_product_id"],
        "mockup_used":              shopify_result["mockup_used"],
        "etsy_product_url":         etsy_product_url,
        "etsy_printify_product_id": etsy_printify_id,
    }
