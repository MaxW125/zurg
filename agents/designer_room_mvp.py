import os
import json
import asyncio
from datetime import datetime
from PIL import Image
import io
from google import genai
from google.genai import types
from agents.llm_client import call_claude, call_claude_haiku
from agents.brain import load_system_prompt, load_prompt
from agents.treasury_mvp import append_fixed_cost_entry
from agents.notify import notify
BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
IMAGEN_MODEL = "imagen-4.0-generate-001"

_PROMPT_FALLBACK = """You are a print-on-demand product designer. Given a niche research brief, you write a detailed image generation prompt for apparel and product designs.

Rules:
- Output ONLY the artwork itself — never show a shirt, clothing, mannequin, model, hanger, or any product mockup
- Design must be a fully isolated graphic on a solid bright magenta (#FF00FF) background — no ground, floor, sky, environment, shadows, or scene-setting elements
- Hard clean edges on the subject — the background remover does a chroma key on the magenta
- Keep it clean and printable — high contrast, no complex gradients
- Be specific about style: flat illustration, bold vector art, watercolor, etc.
- Do NOT include any text or words in the design unless the brief specifically calls for it
- On the very last line write: SHIRT_COLOR: [best base color — choose from: black, white, navy, heather grey, forest green, red, royal blue]
- Output the image prompt first, then SHIRT_COLOR on a new line. Nothing else."""

TRANSPARENCY_SUFFIX = "sticker-style isolated graphic on a solid bright magenta (#FF00FF) background, subject does not touch frame edges, hard clean vector edges with bold dark outline, no soft brush strokes or feathered edges, no shadows or environmental elements, simple bold composition, no magenta or hot-pink tones in the artwork"


_COPY_PROMPT_FALLBACK = """Write Etsy product copy for a {PRODUCT_TYPE} in the "{NICHE}" niche.

Design: {DESIGN}
Target audience: {AUDIENCE}
Seed keywords: {KEYWORDS}{DENIAL_NOTE}

Return ONLY a valid JSON object with these exact keys:
- title: compelling Etsy product title, max 140 chars, keyword-rich and specific (e.g. "Funny Dachshund Mom Coffee Mug — Wiener Dog Lover Gift — Dog Mom Cup")
- description: 2-3 engaging sentences aimed at the niche audience, highlight what makes it special
- tags: array of exactly 13 Etsy tags, relevant and specific, mix of broad and niche terms, max 20 chars each, no duplicates

Raw JSON only. No explanation."""

_IMAGE_PROMPT_FALLBACK = """Write an image generation prompt for a print-on-demand {PRODUCT_TYPE} design.

Niche: {NICHE}
Target audience: {AUDIENCE}
Design direction: {DESIGN_DIRECTION}
Keywords: {KEYWORDS}{DENIAL_NOTE}

Output only the image prompt."""


async def _generate_copy(niche: str, product_type: str, image_prompt: str, target_audience: str, keywords: list, denial_context: str = "") -> dict:
    """Generate Etsy-optimised title, description, and 13 tags via Haiku."""
    denial_note = (
        f"\n\nPREVIOUS COPY WAS REJECTED — Owner feedback: {denial_context}\n"
        "Address this feedback directly in the new copy."
    ) if denial_context else ""

    template = load_prompt("design", "copywriter", _COPY_PROMPT_FALLBACK)
    prompt = (
        template
        .replace("{PRODUCT_TYPE}", product_type)
        .replace("{NICHE}", niche)
        .replace("{DESIGN}", image_prompt[:300])
        .replace("{AUDIENCE}", target_audience)
        .replace("{KEYWORDS}", ", ".join(keywords))
        .replace("{DENIAL_NOTE}", denial_note)
    )

    try:
        raw = await call_claude_haiku(prompt, room="design")
        # Strip markdown fences if present
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        return {
            "title":       str(data.get("title", f"{niche} — {product_type}"))[:140],
            "description": str(data.get("description", "")),
            "tags":        [str(t)[:20] for t in (data.get("tags") or [])[:13]],
        }
    except Exception as e:
        print(f"[designer] Copy generation failed: {e} — using fallback")
        return {
            "title":       f"{niche} — {product_type}",
            "description": "",
            "tags":        keywords[:13],
        }


def _build_prompt_request(brief: dict) -> str:
    denial = brief.get("denial_context", "").strip()
    denial_section = (
        f"\n\nPREVIOUS DESIGN WAS REJECTED — Owner feedback: {denial}\n"
        "Create a new design that directly addresses this feedback. Do not repeat the previous approach."
    ) if denial else ""

    template = load_prompt("design", "designer", _IMAGE_PROMPT_FALLBACK)
    return (
        template
        .replace("{PRODUCT_TYPE}", brief["product_type"])
        .replace("{NICHE}", brief["niche"])
        .replace("{AUDIENCE}", brief.get("target_audience", ""))
        .replace("{DESIGN_DIRECTION}", brief.get("design_direction", ""))
        .replace("{KEYWORDS}", ", ".join(brief.get("keywords", [])))
        .replace("{DENIAL_NOTE}", denial_section)
    )


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
    system = load_system_prompt("design", "designer", _PROMPT_FALLBACK)
    raw_response = await call_claude(prompt_request, system=system, room="design")

    # Parse shirt color recommendation from last line
    shirt_color = "black"
    lines = raw_response.strip().splitlines()
    if lines and lines[-1].upper().startswith("SHIRT_COLOR:"):
        shirt_color = lines[-1].split(":", 1)[1].strip().lower()
        image_prompt = "\n".join(lines[:-1]).strip()
    else:
        image_prompt = raw_response.strip()

    # Step 2 — generate image via Imagen
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    client = genai.Client(api_key=api_key)

    # Enforce transparency suffix even if LLM omits it
    if TRANSPARENCY_SUFFIX not in image_prompt:
        image_prompt = image_prompt.rstrip(". ") + ", " + TRANSPARENCY_SUFFIX

    # Run sync Imagen call in thread so we don't block the event loop
    def _generate():
        return client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=image_prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )

    try:
        response = await asyncio.get_event_loop().run_in_executor(None, _generate)
        raw_bytes = response.generated_images[0].image.image_bytes
    except Exception as imagen_err:
        await notify(f"⚠️ Imagen failed — pipeline stalled\n{str(imagen_err)[:120]}")
        raise
    append_fixed_cost_entry("design", "imagen-4", 0.04)

    # Step 3 — background removal via rembg (neural net subject detection).
    # Falls back to edge flood-fill if rembg fails.
    def _remove_bg():
        from collections import deque
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        pixels = img.load()
        w, h = img.size

        # Detect background color from corners
        corners = [pixels[0,0], pixels[w-1,0], pixels[0,h-1], pixels[w-1,h-1]]
        cr = sum(c[0] for c in corners) // 4
        cg = sum(c[1] for c in corners) // 4
        cb = sum(c[2] for c in corners) // 4
        print(f"[designer] Background color detected: ({cr}, {cg}, {cb})")

        tol = 60

        def is_bg(px):
            return (abs(px[0]-cr) <= tol and
                    abs(px[1]-cg) <= tol and
                    abs(px[2]-cb) <= tol)

        # Flood-fill from edges — removes outer background without touching interior
        visited = [[False]*h for _ in range(w)]
        queue = deque()
        for x in range(w):
            for y in (0, h-1):
                if not visited[x][y] and is_bg(pixels[x,y]):
                    visited[x][y] = True
                    queue.append((x,y))
        for y in range(h):
            for x in (0, w-1):
                if not visited[x][y] and is_bg(pixels[x,y]):
                    visited[x][y] = True
                    queue.append((x,y))
        while queue:
            x, y = queue.popleft()
            pixels[x,y] = (pixels[x,y][0], pixels[x,y][1], pixels[x,y][2], 0)
            for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0 <= nx < w and 0 <= ny < h and not visited[nx][ny] and is_bg(pixels[nx,ny]):
                    visited[nx][ny] = True
                    queue.append((nx,ny))

        # Tight global pass using the detected background color — catches enclosed pockets
        # (letter holes, gaps between legs, mug handles) unreachable from edges.
        # Tolerance 30 against the actual sampled color keeps it safe: orange deviates
        # by ~165 on G, blue by ~255 on R, so no real artwork color gets caught.
        enc_tol = 30
        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                if (a > 0
                        and abs(r - cr) <= enc_tol
                        and abs(g - cg) <= enc_tol
                        and abs(b - cb) <= enc_tol):
                    pixels[x, y] = (r, g, b, 0)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    image_bytes = await asyncio.get_event_loop().run_in_executor(None, _remove_bg)

    # Step 4 — save image
    slug = input.get("niche", "design").lower().replace(" ", "_")[:30]
    image_path = _save_image(image_bytes, slug)

    # Step 5 — generate Etsy copy (title, description, 13 tags)
    copy = await _generate_copy(
        niche=input.get("niche", ""),
        product_type=input.get("product_type", ""),
        image_prompt=image_prompt,
        target_audience=input.get("target_audience", ""),
        keywords=input.get("keywords", []),
        denial_context=input.get("denial_context", ""),
    )

    return {
        "image_path":   image_path,
        "image_prompt": image_prompt,
        "shirt_color":  shirt_color,
        "niche":        input.get("niche", ""),
        "product_type": input.get("product_type", ""),
        "title":        copy["title"],
        "description":  copy["description"],
        "tags":         copy["tags"],
        "model_used":   "claude",
    }
