import os
import base64
import httpx
from agents.llm_client import call_local, call_claude
from agents.printify_client import upload_image, create_product, get_mockup_urls, download_mockup
from agents.product_catalog import get_blueprint
from agents.notify import notify

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
SHOPIFY_API_VERSION = "2025-01"

DESCRIPTION_SYSTEM = """You are a Shopify product copywriter for a print-on-demand store.
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
    # Clamp to black or white — other colors produce unpredictable Printify mockup shades
    _raw_color   = input.get("shirt_color", "black").lower()
    shirt_color  = "white" if _raw_color == "white" else "black"
    blueprint    = get_blueprint(product_type)

    # Step 1 — write product description
    desc_prompt = f"""Write a product description for a {product_type} in the "{niche}" niche.
Design: {input.get('image_prompt', input.get('design_direction', ''))}"""

    model_used = "ollama"
    try:
        description = await call_local(desc_prompt, system=DESCRIPTION_SYSTEM)
    except Exception:
        model_used = "claude"
        description = await call_claude(desc_prompt, system=DESCRIPTION_SYSTEM)

    title = f"{niche} — {product_type}"

    # Step 2 — get Printify mockup (best-effort; falls back to flat design)
    listing_image_path = image_path  # default: use flat design
    printify_product_id = None

    printify_token = os.getenv("PRINTIFY_API_TOKEN", "")
    if printify_token and image_path:
        try:
            disk_path = os.path.join("frontend", "public", image_path.lstrip("/"))
            filename  = os.path.basename(disk_path)

            image_id = await upload_image(disk_path, filename)
            printify_product = await create_product(
                title=title,
                description=description,
                image_id=image_id,
                blueprint_id=blueprint["blueprint_id"],
                print_provider_id=blueprint["print_provider"],
                tags=input.get("keywords", []),
                preferred_color=shirt_color,
            )
            printify_product_id   = printify_product["id"]
            preferred_variant_ids = printify_product.get("_preferred_variant_ids", [])

            mockup_urls = await get_mockup_urls(printify_product_id, preferred_variant_ids=preferred_variant_ids)
            if mockup_urls:
                flat_name   = os.path.splitext(os.path.basename(disk_path))[0]
                mockup_name = f"{flat_name}_mockup.png"
                mockup_disk = os.path.join(os.path.dirname(disk_path), mockup_name)
                await download_mockup(mockup_urls[0], mockup_disk)
                listing_image_path = f"/assets/generated/{mockup_name}"
        except Exception as e:
            import traceback
            print(f"[factory] Printify mockup failed, using flat design: {e}")
            traceback.print_exc()
            listing_image_path = image_path

    # Step 3 — create Shopify draft listing
    product_payload = {
        "product": {
            "title": title,
            "body_html": f"<p>{description}</p>",
            "product_type": product_type,
            "status": "draft",
            "tags": ", ".join(input.get("keywords", [])),
            "variants": [
                {
                    "price": "29.99",
                    "requires_shipping": True,
                    "taxable": True,
                }
            ],
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            _shopify_url("products.json"),
            json=product_payload,
            headers=_shopify_headers(),
        )
        r.raise_for_status()
        product    = r.json()["product"]
        product_id = product["id"]

        if listing_image_path:
            await _attach_image_to_shopify(listing_image_path, product_id, client)

    store          = os.getenv("SHOPIFY_STORE_URL", "")
    product_url    = f"https://{store}/admin/products/{product_id}"
    storefront_url = f"https://{store}/products/{product['handle']}"

    await notify(f"✅ Published: {title}\n{product_url}")

    return {
        "product_id":          product_id,
        "product_url":         product_url,
        "storefront_url":      storefront_url,
        "title":               title,
        "description":         description,
        "model_used":          model_used,
        "printify_product_id": printify_product_id,
        "mockup_used":         listing_image_path != image_path,
    }
