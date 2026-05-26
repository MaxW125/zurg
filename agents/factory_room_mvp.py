import os
import re
import json
import asyncio
from datetime import datetime, timezone, timedelta
from agents.printify_client import upload_image, create_product, download_mockup, publish_product, get_product
from agents.product_catalog import get_blueprint
from agents.notify import notify
from agents.treasury_mvp import append_fixed_cost_entry
import agents.etsy_client as etsy_client

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
FACTORY_LOG_PATH = os.path.join(BRAIN_PATH, "rooms", "factory", "publish_log.jsonl")
_CST = timezone(timedelta(hours=-6))


def _log_publish(title: str, product_type: str, shopify_url: str, etsy_url: str) -> None:
    entry = {
        "ts":           datetime.now(_CST).strftime("%Y-%m-%dT%H:%M:%S"),
        "title":        title,
        "product_type": product_type,
        "shopify_url":  shopify_url or "",
        "etsy_url":     etsy_url or "",
    }
    os.makedirs(os.path.dirname(FACTORY_LOG_PATH), exist_ok=True)
    with open(FACTORY_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")



async def run_factory(input: dict) -> dict:
    """
    Publish an approved design to Shopify (via Printify) and Etsy.

    Pipeline:
      1. Upload flat design image to Printify (shared image_id across both shops)
      2. Create + publish Printify product to Shopify — Printify creates the Shopify
         listing and auto-syncs mockup images when they're generated (async on Printify's side)
      3. Create + publish Printify product to Etsy — same flow, Etsy OAuth required

    Input keys:
      - image_path: web path to the flat design (e.g. /assets/generated/foo.png)
      - niche, product_type, image_prompt, keywords, title, description, tags

    Returns:
      - product_id, product_url, storefront_url, title, model_used
    """
    # Training mode — skip all publishing to avoid fees
    if os.getenv("ZURG_TRAINING_MODE", "").lower() in ("1", "true", "yes"):
        niche        = input.get("niche", "Custom Design")
        product_type = input.get("product_type", "Unisex T-Shirt")
        title        = input.get("title") or f"{niche} — {product_type}"
        description  = input.get("description") or f"{niche} {product_type}"
        print(f"[factory] TRAINING MODE — skipping publish for: {title}")
        await notify(f"🏋️ Training mode: would have published '{title}' to Shopify + Etsy (skipped)")
        return {
            "product_id":               0,
            "product_url":              "#training-mode",
            "storefront_url":           "#training-mode",
            "title":                    title,
            "description":              description,
            "model_used":               "training-mode",
            "printify_product_id":      None,
            "mockup_used":              False,
            "etsy_product_url":         None,
            "etsy_printify_product_id": None,
        }

    niche        = input.get("niche", "Custom Design")
    product_type = input.get("product_type", "Unisex T-Shirt")
    image_path   = input.get("image_path", "")
    blueprint    = get_blueprint(product_type)
    _raw_color   = input.get("shirt_color", blueprint.get("preferred_color", "black")).lower()
    shirt_color  = _raw_color

    title       = input.get("title") or f"{niche} — {product_type}"
    description = input.get("description") or f"{niche} {product_type}"

    printify_token = os.getenv("PRINTIFY_API_TOKEN", "")
    etsy_shop_id   = os.getenv("PRINTIFY_ETSY_SHOP_ID", "")

    # Upload design image to Printify once — shared image_id for both shops
    image_id  = None
    disk_path = os.path.join("frontend", "public", image_path.lstrip("/"))

    if printify_token and image_path:
        try:
            filename = os.path.basename(disk_path)
            image_id = await upload_image(disk_path, filename)
        except Exception as e:
            print(f"[factory] Printify image upload failed: {e}")

    def _select_etsy_images(images: list, preferred_variant_ids: list) -> list[str]:
        """
        Pick the best mockup URLs from a Shopify Printify product for the Etsy listing.
        Stickers: 1 front (first size) + context lifestyle shots.
        Aprons:   1 front (flat) from preferred color + on-person for all colors.
        Totes:    front + person-front for preferred color, then other colors.
        Default:  preferred color images first, max 10.
        """
        preferred_set = set(preferred_variant_ids)
        pt = product_type.lower()

        def label(img):
            src = img.get("src", "")
            return src.split("camera_label=")[-1] if "camera_label=" in src else "unknown"

        def is_preferred(img):
            return bool(preferred_set.intersection(img.get("variant_ids", [])))

        if "sticker" in pt:
            # Sticker variants are sizes not colors — preferred_variant_ids may be empty.
            # Fall back to first variant_id seen in images (smallest size = first generated).
            first = preferred_variant_ids[0] if preferred_variant_ids else None
            if not first:
                for img in images:
                    vids = img.get("variant_ids", [])
                    if vids:
                        first = vids[0]
                        break
            if not first:
                return [img["src"] for img in images if label(img) == "front"][:1]
            first_imgs = [img for img in images if first in img.get("variant_ids", [])]
            front   = [img["src"] for img in first_imgs if label(img) == "front"][:1]
            context = [img["src"] for img in first_imgs if label(img).startswith("context")]
            return front + context

        elif "apron" in pt:
            pref_imgs = [img for img in images if is_preferred(img)] or images
            front     = [img["src"] for img in pref_imgs if label(img) == "front"][:1]
            on_person = [img["src"] for img in images if label(img) == "on-person"]
            return front + on_person

        elif "tote" in pt:
            # Natural flat front first (no model) → then model shots → then other colors.
            pref_imgs  = [img for img in images if is_preferred(img)]
            other_imgs = [img for img in images if not is_preferred(img)]
            result  = [img["src"] for img in pref_imgs  if label(img) == "front"]
            result += [img["src"] for img in pref_imgs  if label(img) == "person-front"]
            result += [img["src"] for img in other_imgs if label(img) in ("front", "person-front")]
            return result

        else:
            pref_imgs  = [img for img in images if is_preferred(img)]
            other_imgs = [img for img in images if not is_preferred(img)]

            # Printify sometimes returns images with empty variant_ids — in that case
            # variant-intersection can't identify the preferred colour. Fall back to
            # checking whether the URL's embedded variant_id is in the preferred set.
            if not pref_imgs and preferred_set:
                import re as _re
                def _url_vid(img):
                    m = _re.search(r'/mockup/[^/]+/(\d+)/', img.get("src", ""))
                    return int(m.group(1)) if m else None
                pref_imgs  = [img for img in images if _url_vid(img) in preferred_set]
                other_imgs = [img for img in images if _url_vid(img) not in preferred_set]

            # Preferred colour images first, then one front per remaining colour
            # (so variation-image linking can assign each colour its own swatch image),
            # then fill remaining slots with lifestyle/back shots up to the 10-image cap.
            other_fronts = []
            seen_front_srcs = set()
            for img in other_imgs:
                if label(img) == "front" and img["src"] not in seen_front_srcs:
                    other_fronts.append(img["src"])
                    seen_front_srcs.add(img["src"])
            other_rest = [img["src"] for img in other_imgs if img["src"] not in seen_front_srcs]
            combined = [img["src"] for img in pref_imgs] + other_fronts + other_rest
            return combined[:10]

    # ── Step 1: Etsy ─────────────────────────────────────────────────────────
    # Run Etsy first — Etsy IS connected so publish triggers mockup generation.
    # We download the mockup here and reuse it for the Shopify listing too,
    # since the Shopify Printify shop may be disconnected and can't generate its own.
    etsy_product_url    = None
    etsy_printify_id    = None
    etsy_listing_id     = None
    etsy_pid            = None
    etsy_preferred      = []
    etsy_variant_color  = {}
    mockup_path         = None   # will be reused by Shopify if found

    if image_id and etsy_shop_id:
        try:
            print(f"[factory] Creating Etsy product in Printify shop {etsy_shop_id}...")
            ep = await create_product(
                title=title,
                description=description,
                image_id=image_id,
                blueprint_id=blueprint["blueprint_id"],
                print_provider_id=blueprint["print_provider"],
                tags=input.get("tags") or input.get("keywords", []),
                preferred_color=shirt_color,
                shop_id=etsy_shop_id,
                retail_price=blueprint.get("retail_price", 2999),
            )
            etsy_pid           = ep["id"]
            etsy_preferred     = ep.get("_preferred_variant_ids", [])
            etsy_variant_color = ep.get("_variant_color_map", {})  # variant_id → color name for this Etsy product
            print(f"[factory] Etsy product created: {etsy_pid} — waiting for mockups before publishing...")

            # Phase 1: poll up to 3 minutes for mockup images BEFORE publishing.
            # Printify starts generating mockups immediately after create_product().
            # Publishing to Etsy before images exist causes Etsy to reject the listing.
            etsy_mock_urls: list[str] = []
            preferred_set = set(etsy_preferred)
            for attempt in range(60):  # 60 * 3s = 180s max
                await asyncio.sleep(3)
                prod   = await get_product(etsy_pid, shop_id=etsy_shop_id)
                images = prod.get("images", [])
                if images:
                    if preferred_set:
                        etsy_mock_urls = [
                            img["src"] for img in images
                            if img.get("src") and preferred_set.intersection(img.get("variant_ids", []))
                        ]
                    etsy_mock_urls = etsy_mock_urls or [img["src"] for img in images if img.get("src")]
                    print(f"[factory] Etsy mockups ready after {(attempt+1)*3}s: {len(etsy_mock_urls)} images")
                    break
            else:
                print(f"[factory] No mockups after 180s — publishing anyway as fallback")

            # Publish to Etsy via Printify
            print(f"[factory] Publishing to Etsy via Printify (mockups={'yes' if etsy_mock_urls else 'no'})...")
            await publish_product(etsy_pid, shop_id=etsy_shop_id)

            # Poll up to 150s for the Etsy listing URL
            etsy_url = None
            for _ in range(50):  # 50 * 3s = 150s
                await asyncio.sleep(3)
                prod   = await get_product(etsy_pid, shop_id=etsy_shop_id)
                handle = (prod.get("external") or {}).get("handle") or ""
                if handle:
                    etsy_url = handle
                    print(f"[factory] Etsy listing live: {etsy_url}")
                    break

            if not etsy_url:
                print(f"[factory] Etsy URL not found after 150s — listing is live but URL not yet in Printify API")
                etsy_url = "https://www.etsy.com/shop/KrakenAndCoDesigns"

            # Download mockup for Shopify
            if etsy_mock_urls:
                flat_name   = os.path.splitext(os.path.basename(disk_path))[0]
                mockup_name = f"{flat_name}_mockup.png"
                mockup_disk = os.path.join(os.path.dirname(disk_path), mockup_name)
                await download_mockup(etsy_mock_urls[0], mockup_disk)
                mockup_path = f"/assets/generated/{mockup_name}"
                print(f"[factory] Mockup downloaded: {mockup_name}")

            # Patch all fields Printify doesn't control
            m = re.search(r'/listing/(\d+)/', etsy_url)
            if m:
                etsy_listing_id = int(m.group(1))
                try:
                    await etsy_client.update_listing(
                        listing_id=etsy_listing_id,
                        product_type=product_type,
                        title=title,
                        description=description,
                        tags=input.get("tags") or input.get("keywords", []),
                    )
                    print(f"[factory] Etsy listing {etsy_listing_id} patched with full field set")
                except Exception as e:
                    print(f"[factory] Etsy listing update failed (non-fatal): {e}")

            append_fixed_cost_entry("factory", "etsy-listing-fee", 0.20)

            etsy_product_url = etsy_url
            etsy_printify_id = etsy_pid
        except Exception as e:
            import traceback
            print(f"[factory] Etsy flow failed: {e}")
            traceback.print_exc()
            await notify(
                "⚠️ Etsy publish error for: " + title + "\n"
                f"Error: {str(e)[:120]}"
            )
    elif not etsy_shop_id:
        print("[factory] Etsy skipped — PRINTIFY_ETSY_SHOP_ID not set")

    # ── Step 2: Shopify ───────────────────────────────────────────────────────
    # Create a Printify product in the Shopify shop and publish it via Printify's
    # OAuth connection — this creates an active Shopify listing without needing
    # a direct Shopify API token.
    async def _shopify_flow() -> dict:
        if not image_id:
            raise RuntimeError("image_id required — Printify upload failed")

        sp = await create_product(
            title=title,
            description=description,
            image_id=image_id,
            blueprint_id=blueprint["blueprint_id"],
            print_provider_id=blueprint["print_provider"],
            tags=input.get("tags") or input.get("keywords", []),
            preferred_color=shirt_color,
            retail_price=blueprint.get("retail_price", 2999),
        )
        pid = sp["id"]
        # variant_id → lowercase color name — used later for Etsy variation-image linking
        shopify_variant_color: dict[int, str] = sp.get("_variant_color_map", {})
        print(f"[factory] Shopify Printify product created: {pid}")

        await publish_product(pid)
        print(f"[factory] Shopify product published via Printify")

        # Poll up to 90s for the Shopify listing URL from Printify
        store = os.getenv("SHOPIFY_STORE_URL", "")
        shopify_url = None
        for _ in range(30):  # 30 * 3s = 90s
            await asyncio.sleep(3)
            prod   = await get_product(pid)
            handle = (prod.get("external") or {}).get("handle") or ""
            if handle:
                shopify_url = handle if handle.startswith("http") else f"https://{store}/products/{handle}"
                print(f"[factory] Shopify listing live: {shopify_url}")
                break

        if not shopify_url:
            shopify_url = f"https://{store}"
            print(f"[factory] Shopify URL not found after 90s — product is live but URL pending")

        # Poll for Shopify's richer mockup set (lifestyle/context/person images).
        # These generate after the standard front mockups — wait up to 120s.
        shopify_preferred = sp.get("_preferred_variant_ids", [])
        shopify_images: list = []
        for _ in range(40):  # 40 * 3s = 120s
            await asyncio.sleep(3)
            sp_prod = await get_product(pid)
            imgs = sp_prod.get("images", [])
            labels = {img.get("src", "").split("camera_label=")[-1] for img in imgs if "camera_label=" in img.get("src", "")}
            if labels - {"front"}:  # at least one non-front image exists
                shopify_images = imgs
                print(f"[factory] Shopify rich mockups ready: {labels}")
                break
        else:
            shopify_images = sp_prod.get("images", []) if sp_prod else []
            print(f"[factory] Shopify rich mockups not ready after 120s — using what's available")

        return {
            "printify_product_id": pid,
            "product_id":          pid,
            "product_url":         shopify_url,
            "storefront_url":      shopify_url,
            "mockup_used":         bool(mockup_path),
            "shopify_images":      shopify_images,
            "shopify_preferred":   shopify_preferred,
            "variant_color":       shopify_variant_color,
        }

    shopify_result = await _shopify_flow()

    # Replace Etsy listing images with curated set.
    # Use the Etsy Printify product's own images — by this point (330s+ into the run)
    # Printify has finished generating mockups for ALL enabled colors on the Etsy product.
    # Using Shopify's mockup set instead would risk getting a partial set (only colors
    # whose mockups finished within the 120s Shopify poll window).
    if etsy_listing_id and etsy_pid:
        try:
            fresh_etsy = await get_product(etsy_pid, shop_id=etsy_shop_id)
            source_images = fresh_etsy.get("images", []) or shopify_result.get("shopify_images", [])
            variant_color = etsy_variant_color  # maps this Etsy product's variant IDs → color names

            # Build color_name → front mockup URL so we can link each color to its image.
            # Printify sometimes sets variant_ids=[] on images — fall back to pulling the
            # variant_id from the URL itself (Printify CDN path: /mockup/<pid>/<vid>/...).
            color_front_urls: dict[str, str] = {}
            for img in source_images:
                if "camera_label=front" not in img.get("src", ""):
                    continue
                vids = img.get("variant_ids", [])
                if not vids:
                    m = re.search(r'/mockup/[^/]+/(\d+)/', img.get("src", ""))
                    if m:
                        vids = [int(m.group(1))]
                for vid in vids:
                    color = variant_color.get(vid, "")
                    if color and color not in color_front_urls:
                        color_front_urls[color] = img["src"]

            selected = _select_etsy_images(
                source_images,
                etsy_preferred,
            )
            if selected:
                print(f"[factory] Replacing Etsy images with {len(selected)} curated mockups...")
                url_to_image_id = await etsy_client.replace_listing_images(etsy_listing_id, selected)
                print(f"[factory] Etsy images updated")

                # Link each color's front image to its Etsy variation value
                if color_front_urls and url_to_image_id:
                    try:
                        prop_id, color_value_map = await etsy_client.get_listing_color_property(etsy_listing_id)
                        if prop_id and color_value_map:
                            variation_images = []
                            for color_name, front_url in color_front_urls.items():
                                img_id   = url_to_image_id.get(front_url)
                                value_id = color_value_map.get(color_name)
                                if img_id and value_id:
                                    variation_images.append({
                                        "property_id": prop_id,
                                        "value_id":    value_id,
                                        "image_id":    img_id,
                                    })
                            if variation_images:
                                await etsy_client.set_variation_images(etsy_listing_id, variation_images)
                                print(f"[factory] Linked {len(variation_images)} color variation images on Etsy")
                    except Exception as e:
                        print(f"[factory] Color variation linking failed (non-fatal): {e}")

                # Mirror same images + order to Shopify so both stores are in sync
                shopify_pid = shopify_result["printify_product_id"]
                shopify_product_id = None
                try:
                    import httpx as _httpx
                    _shopify_hdr = {
                        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
                        "Content-Type": "application/json",
                    }
                    _base = f"https://{os.getenv('SHOPIFY_STORE_URL', '')}/admin/api/2024-04"
                    # Find the Shopify product ID from the external handle URL
                    sp_url = shopify_result.get("product_url", "")
                    handle  = sp_url.rstrip("/").split("/")[-1]
                    async with _httpx.AsyncClient(timeout=30) as _c:
                        r = await _c.get(f"{_base}/products.json?handle={handle}", headers=_shopify_hdr)
                        prods = r.json().get("products", [])
                        if prods:
                            shopify_product_id = prods[0]["id"]
                except Exception as _e:
                    print(f"[factory] Could not resolve Shopify product ID: {_e}")

                if shopify_product_id:
                    try:
                        # Fetch the ranked Etsy images we just uploaded
                        etsy_imgs = await etsy_client.fetch_listing_images(etsy_listing_id)
                        etsy_imgs.sort(key=lambda i: i.get("rank", 99))
                        etsy_urls = [i["url_fullxfull"] for i in etsy_imgs]
                        async with _httpx.AsyncClient(timeout=30) as _c:
                            existing = (await _c.get(
                                f"{_base}/products/{shopify_product_id}/images.json",
                                headers=_shopify_hdr
                            )).json().get("images", [])
                            for img in existing:
                                await _c.delete(
                                    f"{_base}/products/{shopify_product_id}/images/{img['id']}.json",
                                    headers=_shopify_hdr,
                                )
                        async with _httpx.AsyncClient(timeout=60) as _c:
                            for pos, url in enumerate(etsy_urls, start=1):
                                await _c.post(
                                    f"{_base}/products/{shopify_product_id}/images.json",
                                    headers=_shopify_hdr,
                                    json={"image": {"src": url, "position": pos}},
                                )
                        print(f"[factory] Shopify images synced from Etsy ({len(etsy_urls)} images)")
                    except Exception as _e:
                        print(f"[factory] Shopify image sync failed (non-fatal): {_e}")
        except Exception as e:
            print(f"[factory] Etsy image replacement failed (non-fatal): {e}")

    await notify(f"✅ Shopify live: {title}\n{shopify_result['product_url']}")
    if etsy_product_url:
        await notify(f"✅ Etsy live: {title}\n{etsy_product_url}")

    _log_publish(title, product_type, shopify_result["product_url"], etsy_product_url or "")

    return {
        "product_id":               shopify_result["product_id"],
        "product_url":              shopify_result["product_url"],
        "storefront_url":           shopify_result["storefront_url"],
        "title":                    title,
        "description":              description,
        "model_used":               "pre-approved",
        "printify_product_id":      shopify_result["printify_product_id"],
        "mockup_used":              shopify_result["mockup_used"],
        "etsy_product_url":         etsy_product_url,
        "etsy_printify_product_id": etsy_printify_id,
    }


def factory_midnight_report() -> dict:
    today_str = datetime.now(_CST).strftime("%Y-%m-%d")
    today_start = datetime.now(_CST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    report_dir = os.path.join(BRAIN_PATH, "rooms", "factory", "reports")
    publishes_today = []

    if os.path.isfile(FACTORY_LOG_PATH):
        try:
            with open(FACTORY_LOG_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ts_str = entry.get("ts", "")
                        if ts_str and ts_str.startswith(today_str):
                            publishes_today.append({
                                "title":        entry.get("title", ""),
                                "product_type": entry.get("product_type", ""),
                                "has_etsy":     bool(entry.get("etsy_url")),
                            })
                    except Exception:
                        continue
        except Exception:
            pass

    shopify_count = len(publishes_today)
    etsy_count = sum(1 for p in publishes_today if p["has_etsy"])
    nothing = shopify_count == 0

    data = {
        "run_date":          today_str,
        "nothing_to_report": nothing,
        "products_published": shopify_count,
        "shopify_count":     shopify_count,
        "etsy_count":        etsy_count,
        "publishes":         publishes_today,
    }

    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "latest_report.json"), "w") as f:
        json.dump(data, f, indent=2)

    return data
