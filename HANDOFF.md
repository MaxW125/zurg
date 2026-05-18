# Handoff — Session Notes

_Update this before ending a session or starting a new room. One section per session, most recent at top._

---

## Session: 2026-05-18 — Radar Bay

### What We Built
**Radar Bay** — cross-room diagnostic scanner that proposes numbered system improvements (13th room built).

- **`agents/radar_bay_mvp.py`** — loads `latest_report.json` from all 7 data rooms (analytics, pricing, shop_health, cs, war_room, monitoring, media_bay); counts research briefs and approval verdicts from vault; builds a cross-system briefing with per-room age (hours since last report); sends to LLM (Ollama → Claude fallback); parses response into proposals list. Handles two LLM output shapes: `{"proposals": [...]}` (object) and `[...]` (bare array). Also normalises `affectedRoom`/`affected_room` field aliases to `room`. Saves `latest_report.json` + timestamped `.md` to `rooms/radar_bay/reports/`.
- **`routers/radar_bay.py`** — `POST /api/radar-bay/run`, `GET /api/radar-bay/status`
- **`main.py`** — radar_bay router wired in
- **`game.js`** — `radarBayReport` in state; `radarbay: '📡 RADAR BAY'` in titles; added to renders dict; `renderRadarBay`, `_renderRadarBayBody`, `runRadarBay` functions; ROOMS array `gx:1, gy:3, built:true`; proposals rendered with priority colour-coding (P1=red, P2=orange, P3=yellow, P4/5=green)
- **`index.html`** — Radar Bay at col 2, row 4 — coming-soon replaced with live `onclick="openPanel('radarbay')"`
- **Vault** — `rooms/radar_bay/room.md` + `rooms/radar_bay/agents/radar/identity.md` written

### Bugs Hit
- Ollama returned a bare JSON array `[{...}]` instead of the expected object `{"proposals": [...]}`. Fixed by extending the parser to try object form first, then fall back to array form.
- Ollama used `affectedRoom` field instead of `room`. Fixed by normalising all three aliases (`room`, `affectedRoom`, `affected_room`) in post-parse cleanup.

### Current State
- 13 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health, War Room, Monitoring, Media Bay, Radar Bay
- Tested end-to-end: `POST /api/radar-bay/run` scanned all 7 rooms, generated 6 real proposals (stale reports, Anthropic API 401, CS pipeline gap, pricing optimisation)
- `GET /api/radar-bay/status` returns cached report correctly
- Panel renders proposal cards with priority colour-coding; P1–P5 labels shown

### What's Next
- **Armory** — converts approved Radar Bay proposals into SKILL.md files (`gx=0, gy=3`, col 1 row 4)
- Or: **Treasury** — cost tracking per agent, ROI dashboard (`gx=3, gy=3`, col 4 row 4)
- Or: **OpenClaw cron schedule** — Radar Bay Tuesday 6am per the automation plan

### Gotchas for Next Session
- Radar Bay report schema: `run_date`, `model_used`, `rooms_scanned` (list[str]), `proposals` (list), `report_path`
- Proposal schema: `id` (int), `title` (str), `room` (str), `priority` (int 1–5), `description` (str), `rationale` (str)
- LLM sometimes returns `affectedRoom` or bare array — parser handles both, safe to keep as-is
- Radar Bay is standalone/read-only — does not feed any other room or trigger any action
- Grid position: `gx=1, gy=3` (col 2, row 4) — previously the slot shown as `gx=1, gy=3` in the ROOMS array

---

## Session: 2026-05-18 — Media Bay

### What We Built
**Media Bay** — TikTok/Instagram content creation + Publer scheduling (12th room built).

- **`agents/media_bay_mvp.py`** — takes product title, description, type, optional mockup URL; generates TikTok caption (hook + body + 15 hashtags) and Instagram caption (hook + body + 8 hashtags) via LLM (Ollama → Claude fallback); optionally POSTs to Publer API if `PUBLER_API_KEY` set; saves `latest_report.json` + timestamped `.md` to vault at `rooms/media_bay/reports/`. Report schema: `product_title`, `product_type`, `mockup_url`, `tiktok` (hook/caption/hashtags/full_post), `instagram` (hook/caption/hashtags/full_post), `publer_scheduled`, `publer_results`, `model_used`, `run_date`.
- **`routers/media_bay.py`** — `POST /api/media-bay/run`, `GET /api/media-bay/status`
- **`main.py`** — media_bay router wired in
- **`game.js`** — `mediaBayReport` + `autoMediaBay` in state; title `📱 MEDIA BAY`; added to renders dict; `renderMediaBay`, `_renderMediaBayBody`, `runMediaBay`, `_runAutoMediaBay`, `toggleAutoMediaBay`, `copyMediaContent` functions; ROOMS array `gx:1, gy:3, built:true`; auto-chain wired in both manual approval and auto-approval paths (`state.autoMediaBay` flag stored in localStorage)
- **`index.html`** — Media Bay at col 2, row 4 — coming-soon replaced with live `onclick="openPanel('mediabay')"`
- **Vault** — `rooms/media_bay/room.md` + `rooms/media_bay/agents/media_agent/identity.md` written

### Bugs Hit
- LLM (Ollama) returned label format as `* **TIKTOK_HOOK**:` (bullet + bold) instead of clean `TIKTOK_HOOK:`. Fixed by adding `_normalize()` function that strips all markdown decoration from labels before parsing. Uses two regex passes: strip bold/italic from inline labels, collapse block-style heading labels to inline.
- `{1,4}` in regex f-string was being evaluated as Python tuple `(1, 4)` — fixed by using `{{1,4}}` escaping throughout.

### Current State
- 12 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health, War Room, Monitoring, Media Bay
- Tested end-to-end in browser and via API: panel renders correctly at col 4 row 3, Generate form works, cached report pre-fills title, TikTok + Instagram sections with 📋 COPY buttons display correctly
- `POST /api/media-bay/run` returns TikTok hook, caption, hashtags; Instagram hook + caption (hashtags sometimes embedded in caption by LLM — content is still present, just not in separate field)
- `GET /api/media-bay/status` returns cached report correctly
- Publer integration present but untested (no `PUBLER_API_KEY` in env — skips gracefully)
- Grid position corrected after initial build: was gx=1,gy=3 → fixed to gx=3,gy=2 (col 4 row 3)

### What's Next
- **Radar Bay** — proposes system improvements, monitors agent performance (`gx=1, gy=3`, col 2 row 4)
- Or: **Treasury** — cost tracking per agent, ROI dashboard (`gx=3, gy=3`, col 4 row 4)
- Or: **OpenClaw cron schedules** — War Room 7am daily, Monitoring as watchdog

### Gotchas for Next Session
- Media Bay report schema: `product_title`, `product_type`, `mockup_url`, `tiktok` (dict), `instagram` (dict), `publer_scheduled` (bool), `publer_results` (list), `model_used`, `run_date`, `report_path`
- `tiktok` and `instagram` dicts each have: `hook` (str), `caption` (str), `hashtags` (list[str]), `full_post` (str)
- LLM sometimes embeds hashtags inline in caption body instead of on the `INSTAGRAM_HASHTAGS:` label — `hashtags` list may be empty but `full_post` will still contain them
- `_normalize()` handles three label formats: clean (`LABEL: content`), bold-inline (`**LABEL**: content`, `* **LABEL**: content`), and block-heading (`### LABEL\ncontent`, `**LABEL**\ncontent`)
- Publer API endpoint: `POST https://app.publer.io/api/v1/posts` with `Authorization: Bearer {PUBLER_API_KEY}` — untested, may need adjustment when key is available
- Auto-chain: `state.autoMediaBay` localStorage flag; wired to both `approveDesign()` and `_runAutoApprove()` in game.js
- Media Bay is standalone for content generation — does not feed any other room

---

## Session: 2026-05-17 — Monitoring Room

### What We Built
**Monitoring Room** — system health alerts, spend warnings, and API failure detection (11th room built).

- **`agents/monitoring_room_mvp.py`** — no LLM; pure async `httpx` health checks: (1) Server always green since we're responding, (2) Shopify API — GET /shop.json, 401 = token expired, (3) Anthropic API — GET /v1/models, 401 = key invalid, (4) Ollama — GET /api/tags, flags if unreachable, (5) each of the 5 data rooms (analytics, pricing, shop_health, cs, war_room) — checks latest_report.json file age, yellow if >24h or missing. Returns `{ checked_at, overall_status (green/yellow/red), systems[], alerts[], summary }`. Saves to vault at `rooms/monitoring/reports/`.
- **`routers/monitoring.py`** — `POST /api/monitoring/run`, `GET /api/monitoring/status`
- **`main.py`** — monitoring router wired in
- **`game.js`** — `renderMonitoring`, `_renderMonitoringBody`, `runMonitoring`; `monitoringReport` state; `🖥️ MONITORING ROOM` panel title; `monitoring` key in titles/renders; `built: true` at `gx=2, gy=2`
- **`index.html`** — Monitoring Room at col 3, row 3 — coming-soon markup replaced with live `onclick="openPanel('monitoring')"`
- **Vault** — `rooms/monitoring/room.md` updated + `rooms/monitoring/agents/monitor/identity.md` written

### Bugs Hit
- None. Clean build first pass.

### Current State
- 11 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health, War Room, Monitoring
- Monitoring tested end-to-end: `POST /api/monitoring/run` correctly flagged Anthropic API key as 401 (real issue — key needs refreshing), confirmed Shopify token valid, Ollama running with llama3.2, all 5 data room reports within 24h
- `GET /api/monitoring/status` returns cached report correctly
- Both endpoints confirmed in OpenAPI

### Post-Session: Shopify Token Refresh (2026-05-18)
- Shopify token expired overnight (as expected — 24h TTL)
- Ran `shopify store auth`, new token `shpat_REDACTED` dropped into `.env`, server restarted — Shopify returning 200 again
- Anthropic API key still 401 — not needed in dev (Ollama handles all LLM calls), leaving as-is

### What's Next
- **Media Bay** — TikTok/Instagram content creation, Publer scheduling (`gx=3, gy=2, col 4 row 3)
- Or: **OpenClaw cron schedule** — War Room 7am daily, Monitoring as a watchdog

### Gotchas for Next Session
- Monitoring report schema: `checked_at`, `overall_status` (green/yellow/red), `systems` (list with `name`, `key`, `status`, `detail`), `alerts` (list[str]), `summary` (str), `report_path`
- Stale threshold is hardcoded at 24h (`STALE_HOURS = 24` in agent file)
- Room staleness check reads the file's mtime, not a field in the JSON — works even if schemas differ across rooms
- Anthropic API check hits `GET https://api.anthropic.com/v1/models` with `x-api-key` + `anthropic-version: 2023-06-01` headers
- Ollama unavailable = yellow (not red) — Claude fallback handles it, so it's degraded not broken
- Monitoring is standalone — does not feed any other room

---

## Session: 2026-05-17 — War Room

### What We Built
**War Room** — cross-room synthesis + prioritised action plan (10th room built).

- **`agents/war_room_mvp.py`** — loads `latest_report.json` from each built data room (analytics, pricing, shop_health, cs); builds a unified briefing string with per-room summaries; sends to LLM (Ollama → Claude fallback) for synthesis; parses response into `summary`, `fix`, `launch`, `watch` arrays (with a `_flatten()` normaliser that coerces LLM objects to strings); saves `latest_report.json` + timestamped `.md` to vault at `rooms/war_room/reports/`.
- **`routers/war_room.py`** — `POST /api/war-room/run`, `GET /api/war-room/status`
- **`main.py`** — war_room router wired in
- **`game.js`** — `renderWarRoom`, `_renderWarRoomBody`, `runWarRoom`; `warRoomReport` state; `⚔️ WAR ROOM` panel title; `warroom` key in titles/renders; `built: true` at `gx=1, gy=2`
- **`index.html`** — War Room at col 2, row 3 — coming-soon markup replaced with live `onclick="openPanel('warroom')`; Media Bay moved to col 2, row 4
- **Vault** — `rooms/war_room/room.md` + `rooms/war_room/agents/strategist/identity.md` written

### Bugs Hit
- Ollama returned `fix` items as objects (`{"product":..., "action":...}`) instead of strings. Fixed by adding `_flatten()` normaliser that joins dict values with ` — ` separator. All three buckets (fix/launch/watch) now guaranteed to be `list[str]`.

### Current State
- 10 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health, War Room
- War Room tested end-to-end: `POST /api/war-room/run` synthesised all 4 data rooms (analytics, pricing, shop_health, cs) into clean action plan — summary + 1 fix + 2 launch + 1 watch
- `GET /api/war-room/status` returns cached report correctly
- Both endpoints confirmed in OpenAPI

### What's Next
- **Monitoring Room** — system health alerts, spend warnings, API failure detection (`gx=2, gy=2`, col 3 row 3)
- Or: **Media Bay** — TikTok/Instagram content creation, Publer scheduling (`gx=3, gy=2, col 4 row 3)
- Or: **OpenClaw cron schedule** — wire War Room to run daily at 7am

### Gotchas for Next Session
- War Room report schema: `run_date`, `model_used`, `summary` (str), `fix` (list[str]), `launch` (list[str]), `watch` (list[str]), `rooms_included` (list of room keys with data), `report_path`
- Agent identity file: `rooms/war_room/agents/strategist/identity.md` — agent name is "strategist" (not "war_room")
- `_flatten()` normaliser handles LLM returning dicts instead of strings — safe to keep as-is
- War Room is read-only — it only reads other rooms' latest_report.json, never triggers them
- If a room has no report yet, the War Room skips it cleanly (noted as missing in the briefing)
- Grid position is `gx=1, gy=2` (col 2, row 3) — was briefly wrong at `gx=1, gy=3` before fix

---

## Session: 2026-05-17 — Shop Health Room

### What We Built
**Shop Health Room** — listing SEO audit + staleness detection (9th room built).

- **`agents/shop_health_room_mvp.py`** — fetches all active Shopify products + orders; audits each listing for: title length (TITLE TOO SHORT < 20 chars, TITLE TOO LONG > 100 chars), tag count (NEEDS MORE TAGS < 3), description depth (THIN DESCRIPTION < 50 chars), sales staleness (NO SALES 30+ DAYS if live ≥ 30 days with 0 sales, STALE LISTING if last sale ≥ 45 days ago). Sends flagged listings to LLM (Ollama → Claude fallback) for per-product fix recommendations. Saves latest_report.json + timestamped .md to vault at `rooms/shop_health/reports/`.
- **`routers/shop_health.py`** — `POST /api/shop-health/run`, `GET /api/shop-health/status`
- **`main.py`** — shop_health router wired in
- **`game.js`** — `renderShopHealth`, `_renderShopHealthBody`, `runShopHealth`; `shopHealthReport` state; `🏥 SHOP HEALTH ROOM` panel title; `shophealth` key in titles/renders; `built: true` at `gx=0, gy=2`
- **`index.html`** — Shop Health Room at col 1, row 3 — coming-soon markup replaced with live `onclick="openPanel('shophealth')"`
- **Vault** — `rooms/shop_health/room.md` + `rooms/shop_health/agents/shop_health/identity.md` written

### Bugs Hit
- None. Clean build first pass.

### Current State
- 9 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health
- Shop Health tested end-to-end: `POST /api/shop-health/run` correctly audited the live Ferret Enthusiasts T-Shirt (3 days old, 5 tags, 279-char desc → severity: ok, no flags — correct, too new to flag)
- Both `/api/shop-health/run` and `/api/shop-health/status` confirmed in OpenAPI
- `GET /api/shop-health/status` correctly returns the cached report after first run
- Shop Health Room at grid position col 1, row 3 (gx=0, gy=2)

### What's Next
- **Media Bay** — TikTok/Instagram content creation, Publer scheduling (`gx=1, gy=2`, col 2 row 3)
- Or: **War Room** — daily 7am synthesis ritual across all rooms (`gx=1, gy=3`)

### Gotchas for Next Session
- Shop Health report schema: `products_scanned`, `flagged_count`, `model_used`, `run_date`, `products` (list with `product_id`, `title`, `tag_count`, `tags`, `desc_length`, `days_live`, `total_sales`, `days_since_sale`, `issues`, `severity`, `recommendation`)
- Severity values: `"critical"` (NO SALES 30+ DAYS or STALE LISTING), `"warning"` (SEO issues only), `"ok"` (no issues)
- `model_used` is `"none"` when there are no flagged products (LLM skipped cleanly)
- `days_since_sale` is `null` (not 0) when a product has never sold — rendered as "NEVER SOLD" in UI
- Shop Health is standalone — does not feed the main pipeline
- CS Room still needs real orders to test properly (unfulfilled 3+ days, fulfilled 7–60 days, cancelled/refunded)

---

## Session: 2026-05-16 — CS Room

### What We Built
**CS Room** — customer service triage + review request drafting (8th room built).

- **`agents/cs_room_mvp.py`** — fetches all Shopify orders, categorises into two buckets: (1) attention queue (unfulfilled 3+ days, cancelled, refunded/partially_refunded) and (2) review request queue (fulfilled orders 7–60 days old with an email). Batches all orders into one LLM prompt and parses drafted messages back per order. Saves latest_report.json + timestamped .md to vault at `rooms/cs/reports/`.
- **`routers/cs.py`** — `POST /api/cs/run`, `GET /api/cs/status`
- **`main.py`** — cs router wired in
- **`game.js`** — `renderCs`, `_renderCsBody`, `runCs`, `copyCs`; `csReport` state; `🎧 CS ROOM` panel title; `built: true` in ROOMS at `gx=3, gy=1`
- **`index.html`** — CS Room at col 4, row 2 — coming-soon markup replaced with live `onclick="openPanel('cs')"`
- **Vault** — `rooms/cs/room.md` + `rooms/cs/agents/cs/identity.md` written

### Bugs Hit
- `.env` BRAIN_PATH has a space in the path (`Obsidian Vaults/Zurg`) — shell variable expansion with `cut -d= -f2-` strips the path incorrectly. Fixed by hardcoding the path string directly in the bash command with quotes.
- Stray `"\n/"` directory created by the failed first vault attempt. Not committed — excluded from git add.

### Current State
- 8 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS
- CS Room tested end-to-end: `POST /api/cs/run` returns correct JSON (0 orders on fresh store — no Shopify error)
- Both `/api/cs/run` and `/api/cs/status` confirmed in OpenAPI
- CS Room at grid position col 4, row 2 (gx=3, gy=1) — last room in row 2, completing that row

### What's Next
- **Shop Health Room** — listing SEO refresh, stale listing detection (`gx=0, gy=2`, col 1 row 3)
- CS Room can be tested properly once the store has real orders (unfulfilled 3+ days, fulfilled 7–60 days, etc.)

### Gotchas for Next Session
- CS report schema: `attention_orders` (list with `order_number`, `customer_name`, `issue_label`, `product_names`, `order_date`, `total`, `drafted_reply`) and `review_queue` (list with `order_number`, `customer_name`, `product_names`, `fulfilled_date`, `review_message`)
- LLM batch parsing: one prompt for all orders, responses parsed by `[0]`, `[1]`, `[R0]`, `[R1]` prefixes
- CS Room is independent — does not feed into the research → design → approval → factory pipeline
- The stray `"\n/"` directory is still in the working tree (untracked) — can be deleted with `rm -rf $'\n/'` from the zurg directory if it bothers you

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
