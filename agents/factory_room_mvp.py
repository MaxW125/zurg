import os
import base64
import httpx
from agents.llm_client import call_local, call_claude

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


async def _upload_image_to_shopify(image_path: str, product_id: int, client: httpx.AsyncClient) -> str:
    """Read image from disk, base64-encode it, attach to Shopify product. Returns image src URL."""
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
    Publish an approved design directly to Shopify as a draft product listing.

    Printify is used for mockups and fulfillment — wired separately.
    This step creates the Shopify listing with the flat design image.

    Input keys:
      - image_path: web path to the design image
      - niche: niche name
      - product_type: e.g. "Unisex T-Shirt"
      - image_prompt: used to write the description
      - keywords: list of tags

    Returns:
      - product_id, product_url, storefront_url, title, model_used
    """
    niche        = input.get("niche", "Custom Design")
    product_type = input.get("product_type", "Unisex T-Shirt")
    image_path   = input.get("image_path", "")

    # Step 1 — write product description via Ollama (fall back to Claude)
    desc_prompt = f"""Write a product description for a {product_type} in the "{niche}" niche.
Design: {input.get('image_prompt', input.get('design_direction', ''))}"""

    model_used = "ollama"
    try:
        description = await call_local(desc_prompt, system=DESCRIPTION_SYSTEM)
    except Exception:
        model_used = "claude"
        description = await call_claude(desc_prompt, system=DESCRIPTION_SYSTEM)

    title = f"{niche} — {product_type}"

    # Step 2 — create the Shopify product as a draft
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

        # Step 3 — attach the design image
        if image_path:
            await _upload_image_to_shopify(image_path, product_id, client)

    store          = os.getenv("SHOPIFY_STORE_URL", "")
    product_url    = f"https://{store}/admin/products/{product_id}"
    storefront_url = f"https://{store}/products/{product['handle']}"

    return {
        "product_id":     product_id,
        "product_url":    product_url,
        "storefront_url": storefront_url,
        "title":          title,
        "description":    description,
        "model_used":     model_used,
    }
