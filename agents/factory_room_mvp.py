import os
import httpx
from agents.llm_client import call_local, call_claude
from agents.printify_client import upload_image, create_product, publish_to_shopify

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")

DESCRIPTION_SYSTEM = """You are a Shopify product copywriter for a print-on-demand store.
Write a short, compelling product description (2-3 sentences max).
Focus on the niche audience and what makes the design special.
No fluff. Output only the description text."""


async def run_factory(input: dict) -> dict:
    """
    Publish an approved design via Printify → Shopify.

    Pipeline:
      1. Write product description (Ollama → Claude fallback)
      2. Upload design image to Printify media library
      3. Create Printify product with all variants
      4. Publish Printify product to Shopify

    Input keys (from run_designer output, after approval):
      - image_path: web path to design image (e.g. /assets/generated/foo.png)
      - niche: niche name
      - product_type: e.g. "Unisex T-Shirt"
      - image_prompt: used to write the description
      - keywords: list of tags
      - design_direction: optional, used for description

    Returns:
      - product_id: Printify product ID
      - product_url: Shopify admin URL (if store URL configured)
      - title: product title
      - description: generated copy
      - model_used: which LLM wrote the description
    """
    niche        = input.get("niche", "Custom Design")
    product_type = input.get("product_type", "Unisex T-Shirt")
    image_path   = input.get("image_path", "")

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

    # Step 2 — resolve disk path and upload to Printify
    disk_path = os.path.join("frontend", "public", image_path.lstrip("/"))
    filename  = os.path.basename(disk_path)
    image_id  = await upload_image(disk_path, filename)

    # Step 3 — create Printify product
    tags = input.get("keywords", [])
    printify_product = await create_product(
        title=title,
        description=description,
        image_id=image_id,
        tags=tags,
    )
    printify_product_id = printify_product["id"]

    # Step 4 — publish to Shopify via Printify
    await publish_to_shopify(printify_product_id)

    store = os.getenv("SHOPIFY_STORE_URL", "")
    # Printify gives us the external_id (Shopify product ID) after publish;
    # it may take a moment to propagate — return the Printify admin URL as fallback
    shopify_id  = printify_product.get("external", {}).get("id", "")
    product_url = (
        f"https://{store}/admin/products/{shopify_id}"
        if shopify_id and store
        else f"https://app.printify.com/app/shop/{os.getenv('PRINTIFY_SHOP_ID', '')}/products/{printify_product_id}"
    )

    return {
        "product_id":   printify_product_id,
        "product_url":  product_url,
        "title":        title,
        "description":  description,
        "model_used":   model_used,
    }
