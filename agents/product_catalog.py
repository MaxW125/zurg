"""
Printify product catalog — maps product types to blueprint IDs and print providers.

Blueprint IDs confirmed working:
  6    — Bella+Canvas 3001 Unisex T-Shirt       (provider 29: Monster Digital)
  9    — Gildan 18500 Hoodie                    (provider 29: Monster Digital)
  11   — Bella+Canvas 3501 Long Sleeve          (provider 29: Monster Digital)
  49   — Gildan Heavy Blend Crewneck Sweatshirt (provider 39: SwiftPOD)
  478  — Ceramic Mug 11oz/15oz                 (provider 29: Monster Digital)
  1313 — Cotton Canvas Tote Bag                (provider 29: Monster Digital)
  353  — Tumbler 20oz                          (provider 1:  SPOKE Custom Products)
  600  — Die-Cut Stickers                      (provider 73: Printed Simply)
  1447 — Classic Dad Cap                       (provider 99: Printify Choice)
  713  — Cotton Apron                          (provider 6:  T Shirt and Sons)

preferred_color: used to prioritise variant selection in create_product().
  Apparel: "black" (dark shirt shows most designs well)
  Mugs/totes/posters/tumblers: "white" (light surface for full-colour designs)
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
        "print_provider":  39,  # SwiftPOD — Monster Digital (29) never generates mockups for bp49
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
    "Tumbler": {
        "blueprint_id":    353,
        "print_provider":  1,
        "position":        "front",
        "preferred_color": "white",
        "default_colors":  ["white", "black"],
    },
    "Die-Cut Sticker": {
        "blueprint_id":    600,
        "print_provider":  73,
        "position":        "front",
        "preferred_color": "white",
        "default_colors":  ["white"],
    },
    "Classic Dad Cap": {
        "blueprint_id":    1447,
        "print_provider":  99,
        "position":        "front",
        "preferred_color": "black",
        "default_colors":  ["black", "white", "navy"],
    },
    "Cotton Apron": {
        "blueprint_id":    713,
        "print_provider":  6,
        "position":        "front",
        "preferred_color": "black",
        "default_colors":  ["black", "white"],
    },
}

PRODUCT_TYPES = list(CATALOG.keys())

DEFAULT_PRODUCT = "Unisex T-Shirt"


def get_blueprint(product_type: str) -> dict:
    """Return blueprint config for a product type, falling back to t-shirt."""
    return CATALOG.get(product_type, CATALOG[DEFAULT_PRODUCT])
