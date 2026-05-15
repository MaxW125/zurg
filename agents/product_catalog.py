"""
Printify product catalog — maps product types to blueprint IDs and print providers.

Blueprint IDs confirmed working:
  6  — Bella+Canvas 3001 Unisex Jersey T-Shirt (provider 29: Monster Digital)
  9  — Gildan 18500 Heavy Blend Hoodie          (provider 29: Monster Digital)

To add a new product, find its blueprint ID in the Printify catalog at:
  https://developers.printify.com/#catalog
Then run scripts/test_printify.py style checks to confirm provider availability.
"""

CATALOG: dict[str, dict] = {
    "Unisex T-Shirt": {
        "blueprint_id":    6,
        "print_provider":  29,
        "position":        "front",
        "default_colors":  ["black", "white", "navy"],
    },
    "Hoodie": {
        "blueprint_id":    9,
        "print_provider":  29,
        "position":        "front",
        "default_colors":  ["black", "navy", "dark heather"],
    },
    "Long Sleeve T-Shirt": {
        "blueprint_id":    11,
        "print_provider":  29,
        "position":        "front",
        "default_colors":  ["black", "white", "navy"],
    },
}

PRODUCT_TYPES = list(CATALOG.keys())

DEFAULT_PRODUCT = "Unisex T-Shirt"


def get_blueprint(product_type: str) -> dict:
    """Return blueprint config for a product type, falling back to t-shirt."""
    return CATALOG.get(product_type, CATALOG[DEFAULT_PRODUCT])
