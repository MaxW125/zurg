"""
Printify product catalog — maps product types to blueprint IDs and print providers.

Blueprint IDs confirmed working (all via Monster Digital provider 29 except Poster):
  6    — Bella+Canvas 3001 Unisex T-Shirt       (provider 29)
  9    — Gildan 18500 Hoodie                    (provider 29)
  11   — Bella+Canvas 3501 Long Sleeve          (provider 29)
  49   — Gildan Heavy Blend Crewneck Sweatshirt (provider 29)
  478  — Ceramic Mug 11oz/15oz                 (provider 29)
  1313 — Cotton Canvas Tote Bag                (provider 29)
  282  — Matte Vertical Poster                 (provider 2: Sensaria)

preferred_color: used to prioritise variant selection in create_product().
  Apparel: "black" (dark shirt shows most designs well)
  Mugs/totes/posters: "white" (light surface for full-colour designs)
"""

CATALOG: dict[str, dict] = {
    "Unisex T-Shirt": {
        "blueprint_id":    6,
        "print_provider":  29,
        "position":        "front",
        "preferred_color": "black",
        "default_colors":  ["black", "white", "navy"],
    },
    "Hoodie": {
        "blueprint_id":    9,
        "print_provider":  29,
        "position":        "front",
        "preferred_color": "black",
        "default_colors":  ["black", "navy", "dark heather"],
    },
    "Long Sleeve T-Shirt": {
        "blueprint_id":    11,
        "print_provider":  29,
        "position":        "front",
        "preferred_color": "black",
        "default_colors":  ["black", "white", "navy"],
    },
    "Crewneck Sweatshirt": {
        "blueprint_id":    49,
        "print_provider":  29,
        "position":        "front",
        "preferred_color": "black",
        "default_colors":  ["black", "navy", "dark heather"],
    },
    "Ceramic Mug": {
        "blueprint_id":    478,
        "print_provider":  29,
        "position":        "front",
        "preferred_color": "white",
        "default_colors":  ["white"],
    },
    "Tote Bag": {
        "blueprint_id":    1313,
        "print_provider":  29,
        "position":        "front",
        "preferred_color": "natural",
        "default_colors":  ["natural", "white"],
    },
    "Poster": {
        "blueprint_id":    282,
        "print_provider":  2,
        "position":        "front",
        "preferred_color": "white",
        "default_colors":  ["white"],
    },
}

PRODUCT_TYPES = list(CATALOG.keys())

DEFAULT_PRODUCT = "Unisex T-Shirt"


def get_blueprint(product_type: str) -> dict:
    """Return blueprint config for a product type, falling back to t-shirt."""
    return CATALOG.get(product_type, CATALOG[DEFAULT_PRODUCT])
