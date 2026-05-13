import os
import json
import re
from datetime import datetime
from agents.llm_client import call_local, call_claude

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")

SYSTEM = """You are a print-on-demand market researcher. Your job is to identify profitable niche product opportunities for a Shopify store.

You return ONLY a valid JSON object — no markdown, no explanation, no code fences. Just raw JSON.

The JSON must have exactly these keys:
- niche: short name for the niche (e.g. "Axolotl Lovers")
- product_type: what kind of product (e.g. "Unisex T-Shirt")
- target_audience: who buys this (e.g. "teenage girls and young women who love cute aquatic animals")
- keywords: list of 5 search keywords (array of strings)
- design_direction: one sentence describing what the design should look like"""


def _parse_brief(raw: str) -> dict:
    """Extract JSON from model response even if it includes extra text."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Find first {...} block
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response: {raw[:200]}")


def _save_brief(brief: dict) -> str:
    """Write brief to brain/warm/ and return the file path."""
    warm_dir = os.path.join(BRAIN_PATH, "warm")
    os.makedirs(warm_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = brief["niche"].lower().replace(" ", "_")[:30]
    filename = f"brief_{timestamp}_{slug}.md"
    filepath = os.path.join(warm_dir, filename)

    content = f"""# Research Brief: {brief['niche']}
Generated: {datetime.utcnow().isoformat()}

## Niche
{brief['niche']}

## Product Type
{brief['product_type']}

## Target Audience
{brief['target_audience']}

## Keywords
{chr(10).join(f'- {kw}' for kw in brief['keywords'])}

## Design Direction
{brief['design_direction']}
"""
    with open(filepath, "w") as f:
        f.write(content)

    return filepath


async def run_researcher(input: dict) -> dict:
    """
    Find a profitable niche and return a structured brief.

    Input keys (all optional):
      - direction: str  — e.g. "something related to cats" or "" for free choice

    Returns:
      - niche, product_type, target_audience, keywords, design_direction
      - brief_path: where the brief was saved
      - model_used: "ollama" or "claude"
    """
    direction = input.get("direction", "").strip()

    if direction:
        prompt = f"""Find a profitable print-on-demand niche based on this direction: "{direction}"

Pick a specific, passionate audience within that space. Return the JSON brief."""
    else:
        prompt = """Find a profitable print-on-demand niche. Choose something with a passionate, underserved audience.

Avoid generic niches like "dog lovers" — go specific, e.g. "Border Collie agility training enthusiasts".

Return the JSON brief."""

    model_used = "ollama"
    raw = ""
    try:
        raw = await call_local(prompt, system=SYSTEM)
    except Exception:
        model_used = "claude"
        raw = await call_claude(prompt, system=SYSTEM)

    brief = _parse_brief(raw)
    brief_path = _save_brief(brief)

    return {
        "niche": brief["niche"],
        "product_type": brief["product_type"],
        "target_audience": brief["target_audience"],
        "keywords": brief["keywords"],
        "design_direction": brief["design_direction"],
        "brief_path": brief_path,
        "model_used": model_used,
    }
