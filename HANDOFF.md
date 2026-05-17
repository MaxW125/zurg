# Handoff — Session Notes

_Update this before ending a session or starting a new room. One section per session, most recent at top._

---

## Session: 2026-05-17 — Pricing Room

### What We Built
**Pricing Room** — competitor price monitoring + dynamic repricing (7th room built).

- **`agents/pricing_room_mvp.py`** — fetches active Shopify products + orders, computes days-live/days-since-sale per product, runs DDG competitor price search (3 queries), sends to LLM (Ollama → Claude fallback) for per-product RAISE/LOWER/KEEP recommendations, saves report to vault at `rooms/pricing/reports/`
- **`routers/pricing.py`** — `POST /api/pricing/run`, `GET /api/pricing/status`, `POST /api/pricing/apply` (live Shopify variant price update via PUT /variants/{id}.json)
- **`main.py`** — pricing router wired in
- **`game.js`** — `renderPricing`, `_renderPricingBody`, `runPricing`, `applyPrice`, `showApplyPrice`, `hideApplyPrice`; `pricingReport` state; panel title `💰 PRICING ROOM`
- **`index.html`** — Pricing Room at col 3 row 2 (swapped with CS Room, which moves to col 4 row 2); live `onclick="openPanel('pricing')"`
- **Vault** — `rooms/pricing/room.md` + `rooms/pricing/agents/pricing/identity.md` written
- **ROOMS array** — Pricing marked `built: true` at gx=2, gy=1; CS moved to gx=3, gy=1

### Bugs Hit
- Old pricing room had left a `latest_report.json` in the vault with a different schema (from a previous deleted implementation). Deleted it so fresh run starts clean.
- BRAIN_PATH in `.env` has a comment on the same line — grepping with `cut -d= -f2-` picks it up; vault directories created with hardcoded path to avoid the issue.

### Current State
- 7 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing
- Pricing Room tested end-to-end: `POST /api/pricing/run` returns product_stats + LLM analysis
- All three pricing routes confirmed live in OpenAPI
- Pricing Room at grid position col 3, row 2 (gx=2, gy=1)
- CS Room shifted right to col 4, row 2 (gx=3, gy=1)

### What's Next
- **CS Room** — handle Shopify customer messages, order issues, review requests (next room to build)
- **Shop Health Room** — listing SEO refresh, stale listing detection
- Can also do: Factory room background image (replace 🏭 emoji), run 20+ design cycles to build verdict history for Approval Agent learning

### Gotchas for Next Session
- Pricing Room uses `product_stats` (not `products`) and `analysis` (not `recommendations`) in its report JSON — different from the old deleted version
- `POST /api/pricing/apply` takes `{ variant_id: int, new_price: "29.99" }` (price as string, variant_id as int)
- Minimum price floor hardcoded: T-shirt ~$12 base + 40% = ~$16.99 min (enforced by LLM prompt, not in code)

---

## Session: 2026-05-16

### What We Did
- **Restored MacBook working version** as clean foundation — copied all source files from `zurg(macbook_working_version)/`, removed pricing room (pricing_room_mvp.py, routers/pricing.py)
- **Removed venv** — Mac Mini is a dedicated server, switched plist to use `/opt/homebrew/bin/python3` globally, installed requirements with `--break-system-packages`
- **Fixed restart workflow** — created `~/zurg/restart-server.sh` using `launchctl unload/load` pattern (not stop/start)
- **Wired researcher → designer auto-chain** — after every research run, brief is automatically passed to designer. No toggle, always automatic
- **Fixed WhatsApp ↔ browser state sync** — server now saves `last_brief.json` and `last_design.json` to disk after each pipeline run; browser fetches these on panel open so WhatsApp-triggered runs appear in the UI
- **Added two-stage WhatsApp notifications** — immediate ack returned from router, pipeline runs as BackgroundTask, `notify()` sends second text when design is ready
- **Fixed notify.py PATH issue** — launchd strips PATH so `openclaw` and `node` weren't found; hardcoded `/opt/homebrew/bin/openclaw` and pass explicit PATH env to subprocess
- **Fixed `--account zurg` flag** — openclaw broadcast fails silently with this flag; removing it fixed delivery
- **CEO delegation language** — summary prompts now instruct Zurg to speak as the boss who delegated, not the one who did the work
- **Fixed chat scroll** — was scrolling `#chat-history` (not scrollable); fixed to scroll `#panel-body` with 400ms delay to wait for panel slide animation
- **Wrote comprehensive project notes** — full project context for cold-start sessions

### Current State
- Full pipeline works end-to-end: WhatsApp research request → immediate ack → Researcher → Designer → `last_design.json` saved → second WhatsApp text → Approval Room shows design in browser
- Server running on global Homebrew Python, no venv
- 6 rooms built and working: CEO, Research, Design, Approval, Factory, Analytics

### What's Next
- **Pricing Room** — build from scratch (was deleted as part of MacBook restore)
- **Room cleanup** — go through each built room and polish UI/behaviour
- Each new room: update this file before starting

---
