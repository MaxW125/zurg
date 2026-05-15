"""Run this to verify your Printify setup: python3 scripts/test_printify.py"""
import os, asyncio, httpx
from dotenv import load_dotenv

load_dotenv()

BASE    = "https://api.printify.com/v1"
TOKEN   = os.getenv("PRINTIFY_API_TOKEN", "")
SHOP_ID = os.getenv("PRINTIFY_SHOP_ID", "")

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

async def main():
    if not TOKEN:
        print("❌  PRINTIFY_API_TOKEN not set in .env"); return
    if not SHOP_ID:
        print("❌  PRINTIFY_SHOP_ID not set in .env"); return

    async with httpx.AsyncClient(timeout=15) as client:

        # 1 — check token works
        r = await client.get(f"{BASE}/shops.json", headers=headers)
        if r.status_code == 401:
            print("❌  API token is invalid or expired"); return
        r.raise_for_status()
        shops = r.json()
        print(f"✅  Token valid — {len(shops)} shop(s) found:")
        for s in shops:
            print(f"    id={s['id']}  title={s['title']}  sales_channel={s.get('sales_channel','?')}")

        # 2 — check shop ID matches
        ids = [str(s["id"]) for s in shops]
        if SHOP_ID not in ids:
            print(f"❌  PRINTIFY_SHOP_ID={SHOP_ID} not found — available IDs: {ids}"); return
        print(f"✅  Shop ID {SHOP_ID} confirmed")

        # 3 — check blueprint 6 / provider 29 are available
        r2 = await client.get(f"{BASE}/catalog/blueprints/6/print_providers.json", headers=headers)
        providers = r2.json()
        provider_ids = [str(p["id"]) for p in providers]
        if "29" in provider_ids:
            print("✅  Blueprint 6 (Bella+Canvas 3001) + Provider 29 (Monster Digital) — available")
        else:
            print(f"⚠️   Provider 29 not available for blueprint 6. Available providers: {provider_ids[:5]}")
            print("    → Update PRINTIFY_PRINT_PROVIDER in .env to one of those IDs")

asyncio.run(main())
