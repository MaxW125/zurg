# Zurg — TODO

## Done
- [x] Core pipeline: research → design → approval → Shopify
- [x] Pixel art UI with 16-room grid (4×4 map, 4 built rooms)
- [x] Approval Room with agent + auto/manual toggle + verdict storage
- [x] Printify integration (mockup generation, flat design fallback)
- [x] Designer background removal via rembg (real PNG transparency)
- [x] Ollama dev mode (zero Anthropic charges during development)
- [x] Shared chat memory across browser and WhatsApp — last_brief.json + last_design.json bridge WhatsApp-triggered runs to browser UI
- [x] OpenClaw WhatsApp routing fully active — before_dispatch plugin routes all WhatsApp messages through Zurg API; two-stage notifications (immediate ack + design-ready text via notify.py)
- [x] Approval Room — agent + auto/manual toggle + verdict storage + phase 1/2/3 thresholds
- [x] Printify integration — mockup generation with correct shirt color (black default)
- [x] rembg background removal — real PNG transparency on all generated designs
- [x] Product catalog — T-Shirt, Hoodie, Long Sleeve mapped to Printify blueprints
- [x] Full auto pipeline — research always auto-chains to designer → approval (no toggle, always on); WhatsApp and browser both trigger the same pipeline
- [x] 4×4 map expansion — 16 room grid with 11 placeholder rooms
- [x] Autonomous researcher loop — configurable daily cap, delay, live DDG market data, auto-triggers designer
- [x] Analytics Room — live Shopify product/order data, pipeline metrics, LLM insights, delta comparison to previous reports, panel UI
- [x] Analytics Room midnight cron — auto-runs report daily at midnight via system crontab
- [x] Obsidian vault as brain — BRAIN_PATH now points at `~/Desktop/Obsidian Vaults/Zurg`; all agents write reports, briefs, and verdicts directly into Obsidian
- [x] Agent identity system — `agents/brain.py` utility (`load_system_prompt(room, agent, fallback)`) loads room.md + identity.md from vault for all 6 active agents; edit personality in Obsidian, takes effect immediately on next run
- [x] Vault folder structure — 16 room folders under `rooms/`, each with `room.md` (purpose/pipeline context) and `agents/<name>/identity.md` (personality/rules); identity.md files written for all 6 built agents
- [x] Vault cleanup — eliminated `hot/` folder; data reorganised into `rooms/` subfolders: `rooms/research/briefs/`, `rooms/approval/verdicts/`, `rooms/analytics/reports/`, `rooms/captain/` (chat history + Shopify token doc)
- [x] Mac Mini deployment — server running on dedicated machine, global Homebrew Python (no venv), launchd plist configured, restart-server.sh
- [x] project notes + HANDOFF.md — comprehensive cold-start documentation and session handoff system
- [x] Anthropic API key migrated to zurg-account@example.com — Claude fallback live on all agents
- [x] Google Imagen API migrated to zurg-account@example.com — Imagen 4 Fast confirmed generating images
- [x] Printify migrated to zurg-account@example.com — new token + shop ID (<PRINTIFY_SHOP_ID>), Kraken & Co. connected
- [x] Fixed `last_design.json` not updating on direct `/api/rooms/design/run` calls — was only saved via CEO agent path
- [x] Fixed Printify product title bug — `title` variable was clobbered by loop variable in `printify_client.py`, resulting in products named "Ash / 5XL"
- [x] Full pipeline end-to-end verified with new credentials — research → Imagen design → approval → Printify mockup → Shopify draft

---

## Priority List (work through in order)

**P1 — Unblocks everything**
- [x] Migrate all services to zurg-account@example.com — Anthropic ✅, Google ✅, Printify ✅, Publer (deferred — needs Business plan), OpenClaw ✅ (already on prod)
- [x] **Etsy sales channel (publishing)** — Factory Room now publishes every approved design to both Shopify and Etsy in parallel via Printify. `PRINTIFY_ETSY_SHOP_ID=<PRINTIFY_ETSY_SHOP_ID>` in `.env`.
- [x] **Etsy API — market research** — `market_intel.py` now uses Etsy API as fallback data source (Everbee → Etsy API → DDG). Searches 5 niche keyword sets, returns titles/tags/views/favorites from live public listings.
- [x] **Etsy API — shop health audit** — Shop Health Room now audits KrakenAndCoDesigns Etsy listings alongside Shopify. Checks title length, tag count (out of 13), description, views. Etsy section shown in UI panel with clickable listing links.
- [x] **Etsy API — monitoring** — Monitoring Room now checks Etsy API key health alongside all other systems.

**P2 — Makes the system production-ready**
- [ ] LLM audit — right model per agent; Haiku for simple tasks (intent classification, acks), Sonnet for complex (research, briefings). Crosses off the LLM split Final Vision item.
- [ ] Etsy order/revenue data — requires OAuth 2.0 flow (separate from API key). Would unlock Etsy sales in Analytics Room and CS Room. Build when store has real orders.
- [ ] Ideogram + Flux image fallbacks — Imagen fails silently right now; fallbacks mean designs never get stuck
- [ ] Gelato fulfilment fallback — Printify backup
- [ ] Reviews integration — Judge.me or Yotpo

**P3 — Strengthens the platform**
- [ ] ChromaDB — smarter brain; agents can search memory instead of reading flat files
- [ ] Event-driven sprite movement — characters react to pipeline events via SSE
- [ ] Room background images + agent sprites — pixel art PNG per room, sprite per agent

**P4 — Needs real orders first**
- [ ] CS Room end-to-end test — needs unfulfilled 3+ days, fulfilled 7–60 days, cancelled/refunded orders
- [ ] Everbee real market data — code complete, waiting on their Open API approval
- [ ] Etsy order/revenue OAuth — see P2 above

**P5 — Long term**
- [ ] HashiCorp Vault — swap .env secrets; not urgent until real scale
- [ ] Staging environment — second Zurg instance running against test data; swap real API calls for mocked ones via test-mode flags. Prevents buggy agent code from firing real Printify orders or hitting Shopify live. Useful once autonomous publishing is running regularly.

---

## Up Next

### Quick Wins
- [ ] Room background images + agent sprites — pixel art PNG for every room; each room that has an agent also gets a sprite character on the map

### Agent Rooms (build one at a time)
> Finish each room as completely as possible before moving to the next. Room background images and agent sprites can be skipped.
> All new rooms must follow the established patterns:
> - Agent file: `agents/<room>_room_mvp.py` with Ollama → Claude fallback via `agents/llm_client.py`
> - Router file: `routers/<room>.py` registered in `main.py`
> - Identity loaded from vault via `load_system_prompt(room, agent, fallback)` in `agents/brain.py`
> - Room.md + identity.md created in vault at `rooms/<room>/room.md` and `rooms/<room>/agents/<agent>/identity.md`
> - Panel UI added to `frontend/public/game.js` (render function + openPanel title + runX function)
> - Room div updated in `frontend/public/index.html` (remove coming-soon, add onclick)

- [x] Pricing Room — competitor price monitoring, dynamic repricing, margin protection
- [x] CS Room — handle Shopify customer messages, order issues, review requests
  - [ ] End-to-end test once store has real orders (unfulfilled 3+ days, fulfilled 7–60 days, cancelled/refunded)
- [x] Shop Health Room — listing SEO refresh, stale listing detection
- [x] Media Bay — TikTok/Instagram content creation, Publer scheduling (`gx=3, gy=2`, col 4 row 3)
- [x] Monitoring Room — system health alerts, spend warnings, API failure detection (`gx=2, gy=2`, col 3 row 3)
- [x] War Room — daily 7am synthesis ritual, consensus action plan across all rooms
- [x] Radar Bay — proposes system improvements, monitors agent performance
- [x] Armory — converts proposals into SKILL.md files in OpenClaw workspace (`gx=0, gy=3`, col 1 row 4)
- [x] Memory Room — brain compression, ChromaDB re-indexing, cold storage
- [x] Treasury — cost tracking per agent, ROI dashboard, spend guardrails

### Automation
- [x] OpenClaw cron schedules — War Room 7am, CEO 8am, Pricing Monday 6am, Shop Health Wed+Sun 6am, Radar Bay Sunday 6am — all wired via cron_runner.py; daily/weekly mode switchable by texting Zurg
- [ ] Event-driven sprite movement — characters react to pipeline events via SSE

### Account Migration
- [x] Create a new dedicated email for Zurg (separate from personal) — to be used for Shopify, Anthropic, Google (Imagen), Printify, Publer, and all other services
- [x] Replace expiring Shopify token with a permanent one — handled via auto-refresh launchd job (com.zurg.shopify-refresh) every 23 hours. Permanent shpat_ token can be set up later via Custom App in Shopify Admin if needed.

### Infrastructure
- [ ] Wire Everbee real market data into Researcher — code complete, awaiting Everbee Open API approval
- [ ] Look into better research methods (custom Etsy scraper, alternative data sources)
- [ ] LLM audit — pick the best model for each agent (researcher, designer prompt, approval, etc.)
- [ ] Swap flat brain → ChromaDB-indexed Obsidian vault
- [ ] Swap .env secrets → HashiCorp Vault
- [ ] Staging environment with test-mode flags

### Flagged as missing from Final Vision — Max to review
- [x] Real SIM for WhatsApp — verified with temp eSIM, WhatsApp is active and working via OpenClaw
- [x] Telegram + iMessage channels — WhatsApp via OpenClaw is sufficient, additional channels not needed
- [ ] Ideogram + Flux as image generation fallbacks — vision says "Imagen primary, Ideogram fallback, Flux backup"; currently Imagen only with no fallback if it fails
- [ ] Gelato as fulfillment fallback — vision says "Printify (primary), Gelato (fallback)"; only Printify is wired
- [ ] Reviews integration — Judge.me or Yotpo listed in vision tech stack; nothing built or planned
- [ ] LLM split: Haiku for simple tasks, Sonnet for complex — vision specifies two tiers; currently all agents use the same model regardless of complexity

### Gap Items (Final Vision not yet tracked)
- [ ] Approval Engine Phase 2 — reach 100 verdicts with >85% accuracy to unlock agent-predicted approvals (happens through use, no code needed)
- [ ] Spend guardrails — Treasury is built but guardrails need to be tested and verified end-to-end
- [ ] Add Imagen cost logging to Treasury — designer agent should call `append_cost_entry` after each image generation (Imagen 4 Fast: ~$0.02/image)
- [ ] Add Imagen API health check to Monitoring Room — alongside Anthropic/Shopify/Ollama checks
- [ ] Brain reset before go-live — delete all test data: generated images (`frontend/public/assets/generated/`), approval verdicts (`rooms/approval/verdicts/`), research briefs (`rooms/research/briefs/`), all room reports (`rooms/*/reports/`), Treasury ledger (`rooms/treasury/costs.jsonl`), CEO chat history (`rooms/captain/chat_history.json`), `last_brief.json`, `last_design.json`. Do this immediately before switching out of dev mode so prod starts with a clean slate.
- [ ] Publish first real product to Shopify — pipeline exists but nothing live yet
- [ ] 7-day autonomous run — run the system hands-off for 7 days, fix whatever breaks (Definition of Done milestone)
- [ ] Design feedback loop — after 10–20 design cycles, review what Zurg approved/rejected and tune the approval agent's taste model
- [ ] Wire Publer to zurg-account@example.com — account created on zurg-account@example.com but API access requires Business plan ($17/mo); skip until TikTok + Instagram accounts are set up and social posting is a real priority

---

## Key File Locations (for new sessions)

| What | Where |
|------|-------|
| Brain / Obsidian vault | `~/Documents/Obsidian Vaults/Zurg/` |
| Agent identity files | `rooms/<room>/agents/<agent>/identity.md` inside vault |
| Room context files | `rooms/<room>/room.md` inside vault |
| Research briefs | `rooms/research/briefs/brief_*.md` inside vault |
| Approval verdicts | `rooms/approval/verdicts/verdict_*.md` inside vault |
| Analytics reports | `rooms/analytics/reports/` inside vault |
| Researcher loop config | `rooms/research/research_config.json` inside vault |
| CEO chat history | `rooms/captain/chat_history.json` inside vault |
| Shopify token refresh doc | `rooms/captain/shopify-token.md` inside vault |
| BRAIN_PATH env var | `~/zurg/.env` → `BRAIN_PATH=~/Documents/Obsidian Vaults/Zurg` |
| System prompt loader | `agents/brain.py` → `load_system_prompt(room, agent, fallback)` |
| Server | FastAPI on port 9000 — `python main.py` from `~/zurg/` |

## Shopify Token Note
The `SHOPIFY_ACCESS_TOKEN` in `.env` is an **online token that expires every 24 hours**. When the Factory or Analytics agent returns a 401/403 error, run the refresh command in `rooms/captain/shopify-token.md` inside the vault.

---

## Definition of Done (Full System)
- [ ] System runs autonomously for 7 days without errors
- [ ] At least one product published and live on Shopify
- [ ] Approval Engine in Phase 2 (agent predicting correctly)
- [ ] War Room running daily at 7am
- [ ] WhatsApp alerts working for all critical events
- [ ] Spend guardrails tested and verified
- [ ] All secrets in Vault — zero in code
- [ ] ChromaDB indexing brain with customers/ excluded
- [ ] Treasury showing real cost breakdown per agent
- [ ] Radar Bay generating improvement proposals
- [ ] Armory storing at least one self-generated skill

---

## Maintenance
- [ ] Audit all rooms for functionality and security
