import os
import asyncio
from datetime import datetime
from google import genai
from google.genai import types
from agents.llm_client import call_local, call_claude

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
IMAGEN_MODEL = "imagen-4.0-fast-generate-001"

PROMPT_SYSTEM = """You are a print-on-demand product designer. Given a niche research brief, you write a detailed image generation prompt for a t-shirt or apparel design.

Rules:
- The design must work on a plain white or transparent background
- Keep it clean and printable — no gradients that won't transfer well
- Be specific about style: flat illustration, vector art, watercolor, etc.
- Do NOT include any text or words in the design unless the brief specifically calls for it
- Output ONLY the image prompt — no explanation, no preamble"""


def _build_prompt_request(brief: dict) -> str:
    return f"""Write an image generation prompt for a print-on-demand {brief['product_type']} design.

Niche: {brief['niche']}
Target audience: {brief['target_audience']}
Design direction: {brief['design_direction']}
Keywords: {', '.join(brief['keywords'])}

Output only the image prompt."""


def _save_image(image_bytes: bytes, slug: str) -> str:
    """Save image to frontend/public/assets/generated/ and return the web path."""
    out_dir = os.path.join("frontend", "public", "assets", "generated")
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{slug}.png"
    filepath = os.path.join(out_dir, filename)

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    return f"/assets/generated/{filename}"


async def run_designer(input: dict) -> dict:
    """
    Generate a product design image from a research brief.

    Input keys (from run_researcher output):
      - niche, product_type, target_audience, keywords, design_direction

    Returns:
      - image_path: web-accessible path e.g. /assets/generated/....png
      - image_prompt: the prompt used to generate the image
      - niche: passed through for approval step
      - product_type: passed through
      - model_used: which LLM built the prompt
    """
    # Step 1 — build image prompt via Ollama (fall back to Claude)
    prompt_request = _build_prompt_request(input)
    model_used = "ollama"
    try:
        image_prompt = await call_local(prompt_request, system=PROMPT_SYSTEM)
    except Exception:
        model_used = "claude"
        image_prompt = await call_claude(prompt_request, system=PROMPT_SYSTEM)

    # Step 2 — generate image via Imagen
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    client = genai.Client(api_key=api_key)

    # Run sync Imagen call in thread so we don't block the event loop
    def _generate():
        return client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=image_prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )

    response = await asyncio.get_event_loop().run_in_executor(None, _generate)
    image_bytes = response.generated_images[0].image.image_bytes

    # Step 3 — save image
    slug = input.get("niche", "design").lower().replace(" ", "_")[:30]
    image_path = _save_image(image_bytes, slug)

    return {
        "image_path": image_path,
        "image_prompt": image_prompt,
        "niche": input.get("niche", ""),
        "product_type": input.get("product_type", ""),
        "model_used": model_used,
    }
