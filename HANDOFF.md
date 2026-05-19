# Handoff — Session Notes

_Update this before ending a session or starting a new room. One section per session, most recent at top._

---

## Session: 2026-05-19 — Service Migration + Pipeline Fixes

### What We Did
- Migrated Anthropic API key to zurg-account@example.com — Claude fallback now live on all agents (was 401 all session)
- Migrated Google Imagen API to zurg-account@example.com via AI Studio — Imagen 4 Fast confirmed generating images
- Migrated Printify to zurg-account@example.com — new token, new shop ID (<PRINTIFY_SHOP_ID>), Kraken & Co. reconnected to Shopify
- Deferred Publer migration — API requires Business plan ($17/mo); skip until TikTok + Instagram accounts exist
- OpenClaw already on prod — no migration needed
- Fixed `.env` whitespace — all keys had stray leading spaces, cleaned up
- Gitignored `backups/` and `brain/rooms/` (runtime data), committed `refresh-shopify-token.sh`
- Fixed `last_design.json` not updating on direct `/api/rooms/design/run` calls — router now writes it after every design run
- Fixed critical Printify title bug in `agents/printify_client.py` — loop variable `title` was clobbering the product title parameter, causing products to be published as "Ash / 5XL". Fixed by renaming loop var to `vtitle`
- Verified full end-to-end pipeline with new credentials: research → Imagen design → approval → Printify mockup → Shopify draft (test product created and deleted)

### Bugs Fixed
- **Printify title clobber** (`agents/printify_client.py` line ~120): `for v in variants: title = v.get("title", "")` overwrote the `title` parameter. Renamed to `vtitle`. This was causing every published product to have a variant name as its title and 0 mockup images.
- **`last_design.json` not saved on direct design runs** (`routers/rooms.py`): `/api/rooms/design/run` wasn't writing `last_design.json`, so the Approval Room in the browser kept showing the old design after a fresh run. Fixed by writing the file in the router after every design call.

### Current State
- All credentials live on zurg-account@example.com: Anthropic ✅, Google ✅, Printify ✅, Shopify ✅, OpenClaw ✅
- Full pipeline verified working end-to-end with real Imagen images and real Printify mockups
- Monitoring shows all systems green (Anthropic, Shopify, Ollama all healthy)
- Publer account created on zurg-account@example.com but API deferred (needs paid plan + social accounts first)

### What's Next
**P2 — LLM audit** is the natural next step now that Claude is live:
- Audit each agent and assign the right model: Haiku for simple tasks (intent classification, acks, CS replies), Sonnet for complex (research briefs, War Room synthesis, approval analysis)
- This directly reduces cost and improves speed for lightweight agents
- File to edit: `agents/llm_client.py` — add `call_claude_haiku()` function, then update each agent

**Or: Imagen cost logging in Treasury** — quick win now that Imagen is actually running:
- `agents/designer_room_mvp.py` — call `append_cost_entry("design", "imagen-4-fast", 0, 0)` with a fixed cost per image (~$0.02) after each successful generation
- `agents/treasury_mvp.py` — add Imagen as a separate cost category (fixed per-image, not per-token)

### Gotchas
- Printify shop ID changed: old was `<OLD_PRINTIFY_SHOP_ID>` (personal account), new is `<PRINTIFY_SHOP_ID>` (zurg account) — already updated in `.env`
- The Printify title bug was silent — products were created and published with wrong titles and no mockup images. Always check Factory Room output for `mockup_used: true`
- `last_design.json` is now written by both `routers/rooms.py` (direct design runs) and `agents/ceo_room_mvp.py` (CEO-delegated runs) — both paths are covered
- Google Imagen requires billing enabled on the AI Studio project — free tier blocks Imagen even with a valid key

---

## Session: 2026-05-18 — Todo Cleanup + Priority List

### What We Did
- Wired and verified all 6 cron jobs via `cron_runner.py` (War Room 7am, CEO 8am, Analytics midnight, Pricing Mon 6am, Shop Health Sun+Wed 6am, Radar Bay Sun 6am)
- Fixed cron briefings bypassing intent classification (was misrouting briefing prompts as research jobs)
- Fixed `notify.py` success check that was logging false failures
- Removed dead Shopify OAuth callback with hardcoded credentials from `main.py`
- Added daily/weekly reporting mode — text Zurg "switch to weekly" to accumulate Mon–Sat, send one Sunday summary
- Audited TODO against Final Vision — added Gap Items section and a Priority List
- Checked off: cron schedules, Zurg email, Shopify token, WhatsApp SIM, Telegram/iMessage

### Current State
- All 16 rooms built, all cron jobs scheduled and verified working
- First real briefing delivered via WhatsApp — content correct, quality limited by Ollama (Anthropic API key is 401)
- `reporting_config.json` initialised to `{"mode": "daily"}`
- TODO has a clean Priority List (P1–P5) to work from next session

### What's Next
**P1 — Migrate all services to zurg-account@example.com:**
Anthropic (fixes 401 + unlocks Claude), Google (Imagen), Printify, Publer, OpenClaw

**P2 after that:**
- LLM audit (Haiku vs Sonnet per agent)
- Ideogram + Flux image fallbacks
- Gelato fulfilment fallback
- Reviews integration

### Gotchas
- Cron briefings use `source="cron_briefing"` — this bypasses intent classification in `chat.py` and goes straight to LLM. Do not remove this path.
- Weekly log lives at `rooms/captain/weekly_briefings.json` — cleared after Sunday send
- `notify.py` returncode check is now just `== 0` (was incorrectly checking for "0 failed" string)

---

## Session: 2026-05-18 — Cron Schedules + Reporting Mode

### What We Built
**`cron_runner.py`** — single entry point for all scheduled jobs. All cron logic lives here; nothing is split across other files.

**Schedule (system crontab — `crontab -e` to view):**
- War Room: daily 7am
- CEO briefing: daily 8am
- Analytics: daily midnight
- Pricing: Monday 6am
- Shop Health: Sunday + Wednesday 6am
- Radar Bay: Sunday 6am

**How the CEO briefing works:**
- `cron_runner.py --job ceo` reads the latest `reports/latest_report.json` from all rooms, builds a context-rich prompt, POSTs to `/api/chat/ceo/instruct`, and calls `notify()` with the response
- Zurg texts you the combined report — you never hear from individual rooms directly

**Daily/weekly mode:**
- Default is daily. Text Zurg "switch to weekly" or "go daily" — he writes to `rooms/captain/reporting_config.json` and confirms
- Weekly mode: Mon–Sat CEO runs silently, appends daily summary to `rooms/captain/weekly_briefings.json`. Sunday it reads all 7, sends one combined report, clears the log.

**Critical error alerts:**
- If any room returns a 401/403/auth error, `cron_runner.py` routes an urgent message through the CEO → Zurg texts you immediately in his own voice

**CEO agent change (`agents/ceo_room_mvp.py`):**
- Added `set_reporting` intent to classifier + handler that writes `reporting_config.json`

### Current State
- All 16 rooms built, all 6 cron jobs wired and scheduled
- `reporting_config.json` initialised to `{"mode": "daily"}`
- Anthropic API key still 401 — agents fall back to Ollama. Briefings will work but quality depends on local model

### What's Next
- **Verify a real briefing** — wait for 8am or manually run `python3 cron_runner.py --job ceo` to test end-to-end
- **Fix Anthropic API key** — account migration (Google, Printify, Everbee, OpenClaw, Publer still to migrate)
- **Real SIM for WhatsApp** — briefings are ready but WhatsApp requires a dedicated SIM (Google Voice doesn't work)
- **ChromaDB integration** — stub is ready in memory_room_mvp.py
- **Approval Engine Phase 2** — need ~100 verdicts with >85% accuracy

### Gotchas
- `cron_runner.py` loads `.env` via python-dotenv — BRAIN_PATH must be set there or it falls back to hardcoded path
- Weekly log (`weekly_briefings.json`) is cleared after Sunday send — if Sunday CEO crashes mid-run, log is not cleared and will carry over to next week (harmless but worth knowing)
- The crontab no longer has the old `curl` analytics entry — replaced by `cron_runner.py --job analytics`
- `main.py` has an uncommitted `/auth/callback` endpoint with hardcoded Shopify App credentials — left from the token refresh session, should be cleaned up

---

## Session: 2026-05-18 — Shopify Token Automation

### What We Did
- Solved the Shopify token problem: `shopify store auth` runs headlessly when a valid session exists — no browser required
- Verified the refresh script (`~/zurg/refresh-shopify-token.sh`) works end-to-end: refreshes token, updates `.env`, restarts server
- launchd job (`com.zurg.shopify-refresh`) already installed, fires every 23 hours automatically
- Confirmed new store (Kraken & Co., your-store.myshopify.com) is live via API — returns correct store name and zurg-account@example.com
- Documented full runbook in brain: `Obsidian Vaults/Zurg/shopify-token-runbook.md`
- Old dev store (your-store.myshopify.com) is safe to delete — nothing points to it

### Current State
- **All 16 rooms fully built and working**
- **Shopify fully migrated** to Kraken & Co. on zurg-account@example.com, token auto-refreshes
- Anthropic API key is currently 401 — Treasury logs zeros, all agents fall back to Ollama. Will be fixed when account migration continues (Google, Printify, Everbee, OpenClaw, Publer still to migrate)
- OpenClaw cron jobs not yet set up — all rooms still require manual triggers

### What's Next
**OpenClaw cron schedules** — this is the biggest autonomy unlock remaining. Wire the following jobs:
- War Room: daily 7am
- CEO: daily 8am (reads War Room output, issues instructions)
- Analytics: Sunday 11pm
- Pricing: Monday 6am
- Shop Health: Wednesday 6am
- Radar Bay: Tuesday 6am

Each cron job needs to POST to the relevant API endpoint (e.g. `POST http://localhost:9000/api/war-room/run`) and optionally trigger a WhatsApp notification via `notify.py` when done.

OpenClaw cron config lives at `~/.openclaw/openclaw.json`. Check OpenClaw docs or existing config for the cron job schema before writing anything.

### Gotchas for Next Session
- Server runs on port 9000 — OpenClaw gateway runs on port 8000, don't confuse them
- `notify.py` requires the full PATH env var passed to subprocess (launchd strips PATH) — already handled in the existing notify.py
- Never pass `--account zurg` to openclaw broadcast — breaks delivery silently
- Shopify token is handled — DO NOT touch the refresh script or launchd plist
- If Shopify token ever needs manual recovery: run `shopify store auth --store your-store.myshopify.com --scopes read_all_orders,...` then `bash ~/zurg/refresh-shopify-token.sh`

---

## Session: 2026-05-18 — Memory Room

### What We Built
**Memory Room** — vault stats, compression, cold storage export, ChromaDB stub re-indexing (16th and final planned room built).

- **`agents/memory_room_mvp.py`** — four pure-filesystem functions (no LLM):
  - `get_vault_stats()`: walks `rooms/*/`, counts briefs (97), verdicts (29), archived reports, skills (OpenClaw + vault mirror), total .md files (186), per-room file sizes sorted by size, grand total KB.
  - `compress_vault(keep_n=5)`: for each `rooms/*/reports/`, sorts timestamped files (excludes `latest_report.json`), keeps newest `keep_n`, moves older ones to `rooms/<room>/archive/`. Returns rooms_scanned, files_archived, bytes_freed.
  - `export_cold_storage()`: zips entire vault (excluding `/customers/`) to `~/zurg/backups/vault_TIMESTAMP.zip`. Returns path, files_zipped, zip_mb.
  - `run_index()`: recursively scans all `.md` files, skips `/customers/`, records room/filename/path/char_count/preview_100 per file, writes `rooms/memory/index_log.json` with full entries list + summary. Returns summary only (entries list stays on disk).
- **`routers/memory.py`** — `GET /api/memory/stats`, `POST /api/memory/compress`, `POST /api/memory/export`, `POST /api/memory/index`
- **`main.py`** — memory router wired in
- **`game.js`** — `memoryStats` in state; `memory: '🧠 MEMORY ROOM'` in titles; added to renders dict; ROOMS array `gx:2, gy:3, built:true`; `renderMemory`, `_renderMemoryBody`, `refreshMemoryStats`, `runMemoryCompress`, `runMemoryExport`, `runMemoryIndex` functions; panel has 4-stat grid (briefs/verdicts/archived reports/skills), file size table by room, compress form with keep_n input, export button, index button.
- **`index.html`** — Memory Room at col 3, row 4 — coming-soon replaced with live `onclick="openPanel('memory')"`
- **Vault** — `rooms/memory/room.md` updated to "built"; `rooms/memory/agents/memory/identity.md` written

### Bugs Hit
- None. Clean build first pass. All four endpoints verified working end-to-end.

### Current State
- **All 16 rooms built**: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health, War Room, Monitoring, Media Bay, Radar Bay, Armory, Treasury, Memory
- `GET /api/memory/stats` returns: 97 briefs, 29 verdicts, 0 archived reports (none to compress yet), 0 skills, 186 total .md files, 168.3 KB total, 15 rooms in size table
- `POST /api/memory/compress` returns: 9 rooms_scanned, 0 files_archived (nothing old enough to archive — all rooms only have `latest_report.json`)
- `POST /api/memory/export` created `~/zurg/backups/vault_20260518_192303.zip` — 207 files, 135 KB compressed
- `POST /api/memory/index` scanned 186 files, 117.9 KB total chars, wrote `rooms/memory/index_log.json`
- `~/zurg/backups/` directory created as a side-effect — not committed (gitignored by virtue of not being staged)

### What's Next
All 16 rooms are built. Remaining work is in automation and infrastructure:
- **OpenClaw cron schedules** — War Room 7am daily, Radar Bay Tuesday 6am, CEO 8am, Pricing Monday 6am, Shop Health Wednesday 6am
- **Run real Claude calls** — fix Anthropic API key (currently 401), run a full pipeline to see Treasury populate with live cost data
- **ChromaDB integration** — install `chromadb`, wire `run_index()` to actually upsert documents into a collection (stub is ready)
- **Approval Engine Phase 2** — need ~100 verdicts with >85% accuracy to unlock
- **Everbee wire-up** — code complete, awaiting API approval

### Gotchas for Next Session
- Memory Room is standalone — does not feed any other room, no LLM used
- `compress_vault` is idempotent: re-running with the same `keep_n` on an already-compressed vault archives nothing
- `latest_report.json` is explicitly excluded from compression — safe to run at any time
- `index_log.json` at `rooms/memory/index_log.json` is large (~186 entries with previews) — the API endpoint returns only the summary, not the full entries list; read the file directly in Obsidian to inspect
- Cold storage zips to `~/zurg/backups/` (not inside BRAIN_PATH) — directory is created on first export, not committed to git
- `skills_count` counts both `~/.openclaw/skills/*.md` and vault mirror `rooms/armory/skills/*.md` — currently 0 because no skills have been forged yet
- `reports_count` in stats counts non-`latest_report.json` JSON files in `rooms/*/reports/` — currently 0 because all rooms only have `latest_report.json` (timestamped reports are only created when rooms have been run multiple times)

---

## Session: 2026-05-18 — Treasury

### What We Built
**Treasury** — cost tracking, ROI dashboard, and daily spend guardrail (15th room built).

- **`agents/treasury_mvp.py`** — `get_report()`: reads `costs.jsonl`, returns total_spend, today_spend, daily_cap_usd, cap_hit_today, total_runs, avg_cost, revenue (from analytics), roi (revenue/spend), by_room list. `get_config()` / `set_config()`: reads/writes `treasury_config.json`. `append_cost_entry(room, model, tokens_in, tokens_out)`: appends one JSONL line with ts/room/model/tokens_in/tokens_out/cost_usd. `check_daily_cap()`: raises `RuntimeError("daily_cap_exceeded: ...")` if today's spend ≥ cap. `get_today_spend()`: sums cost_usd for entries whose ts starts with today's ISO date.
- **`agents/llm_client.py`** — `call_claude()` now takes an optional `room: str = "unknown"` param. Calls `_check_cap()` before the API call (cap breach raises RuntimeError, which callers' `except Exception` catches → stays on Ollama). After a successful call, calls `_log_cost(room, tokens_in, tokens_out)` using `message.usage.input_tokens` / `message.usage.output_tokens` from the Anthropic response. Both helpers import `treasury_mvp` lazily and swallow all errors so they never block agent calls.
- **All 13 agent files** — each `call_claude()` fallback call updated with `room=` keyword arg: ceo, research, design, factory, approval, analytics, pricing, cs, shophealth, warroom, mediabay, radarbay, armory.
- **`routers/treasury.py`** — `GET /api/treasury/report`, `GET /api/treasury/config`, `POST /api/treasury/config`
- **`main.py`** — treasury router wired in
- **`game.js`** — `treasuryReport` in state; `treasury: '💎 TREASURY'` in titles; added to renders dict; `renderTreasury`, `_renderTreasuryBody`, `refreshTreasury`, `saveTreasuryCap` functions; ROOMS array `gx:3, gy:3, built:true`; panel has 4-stat grid (total spend, ROI, revenue, avg cost/run), today progress bar (green→yellow→red), by-room table with run counts, daily cap config form.
- **`index.html`** — Treasury at col 4, row 4 — coming-soon replaced with live `onclick="openPanel('treasury')"`
- **Vault** — `rooms/treasury/room.md` updated; `rooms/treasury/agents/treasurer/identity.md` written; `rooms/treasury/costs.jsonl` (append-only ledger); `rooms/treasury/treasury_config.json`

### Bugs Hit
- None. Clean build first pass. All three endpoints verified working end-to-end.

### Current State
- 15 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health, War Room, Monitoring, Media Bay, Radar Bay, Armory, Treasury
- `GET /api/treasury/report` returns correct zero-state when ledger is empty
- `GET /api/treasury/config` returns `{"daily_cap_usd": 1.0}` (default)
- `POST /api/treasury/config` writes config and returns new value
- Cost logging verified: `append_cost_entry("research", "claude-sonnet-4-6", 1200, 400)` returns `$0.009600` (1200 × $0.000003 + 400 × $0.000015 — Sonnet 4.6 rates)
- Daily cap tested: setting cap below current spend raises `RuntimeError` correctly
- Ledger is clean (test entries removed)

### What's Next
- **Memory Room** — brain compression, ChromaDB re-indexing, cold storage (`gx=2, gy=3`, col 3 row 4)
- Or: **OpenClaw cron schedules** — War Room 7am, Radar Bay Tuesday 6am, etc.
- Or: **Run real Claude calls** (fix Anthropic API key, run a pipeline) to see Treasury populate with live data

### Gotchas for Next Session
- Ledger path: `$BRAIN_PATH/rooms/treasury/costs.jsonl` — append-only, never overwrite
- Config path: `$BRAIN_PATH/rooms/treasury/treasury_config.json` — just `{"daily_cap_usd": float}`
- Cost rates hardcoded in `treasury_mvp.py`: `COST_PER_INPUT_TOKEN = 3.00/1_000_000`, `COST_PER_OUTPUT_TOKEN = 15.00/1_000_000` (Sonnet 4.6 pricing)
- Daily cap of `0` = disabled (check explicitly skipped). Setting cap below current spend immediately blocks Claude for the rest of the day.
- Cap check uses `_check_cap()` in `llm_client.py` which imports treasury lazily — no circular import issues, and import errors are swallowed silently so a broken vault never blocks agents.
- Streaming (`call_claude_stream`) is NOT instrumented — only used for CEO browser chat, token counts aren't easily captured from streaming. All agent non-streaming calls are logged.
- Revenue for ROI comes from `rooms/analytics/reports/latest_report.json` → `revenue_total` field. If analytics has never run, `revenue` in the report is `0.0` and `roi` is `null`.

---

## Session: 2026-05-18 — Armory

### What We Built
**Armory** — converts Radar Bay proposals into versioned SKILL.md files in the OpenClaw workspace (14th room built).

- **`agents/armory_mvp.py`** — `generate_skill(proposal_id)`: loads latest Radar Bay report, finds the proposal by ID, builds a versioned system prompt, sends to LLM (Ollama → Claude fallback), strips any preamble before the frontmatter, returns preview dict (`proposal_id`, `proposal_title`, `slug`, `version`, `content`, `model_used`). `save_skill(content, slug, version)`: writes to `~/.openclaw/skills/<slug>_v<n>.md` and mirrors to vault `rooms/armory/skills/`, updates `rooms/armory/reports/latest_report.json` log. `get_skills_list()`: reads all `.md` files from SKILLS_DIR, parses frontmatter for name/version/description, returns sorted list. `_get_next_version(slug)`: counts `slug_v*.md` files to determine next version — always +1, never overwrites.
- **`routers/armory.py`** — `POST /api/armory/generate`, `POST /api/armory/save`, `GET /api/armory/skills`
- **`main.py`** — armory router wired in
- **`game.js`** — `armorySkills`, `armoryPreview` in state; `armory: '⚔️ ARMORY'` in titles; added to renders dict; `renderArmory`, `_renderArmoryBody`, `generateSkill(proposalId)`, `saveSkill()`, `cancelSkillPreview()`, `refreshArmorySkills()` functions; ROOMS array `gx:0, gy:3, built:true`; proposal cards show Radar Bay proposals with ⚒ FORGE button; preview shown inline with raw SKILL.md content; Confirm & Save / Cancel buttons; saved skills list at bottom.
- **`index.html`** — Armory at col 1, row 4 — coming-soon replaced with live `onclick="openPanel('armory')"`
- **Vault** — `rooms/armory/room.md` updated + `rooms/armory/agents/armory/identity.md` written; `rooms/armory/reports/` and `rooms/armory/skills/` directories created

### Bugs Hit
- None. Clean build first pass. All three endpoints verified working end-to-end via curl.

### Current State
- 14 rooms fully built and working: CEO, Research, Design, Approval, Factory, Analytics, Pricing, CS, Shop Health, War Room, Monitoring, Media Bay, Radar Bay, Armory
- `POST /api/armory/generate` with `{"proposal_id": 1}` returns correct preview dict (tested against live Radar Bay report)
- `POST /api/armory/save` writes file to `~/.openclaw/skills/` and mirrors to vault (verified file created)
- `GET /api/armory/skills` returns skills list with parsed frontmatter (verified after save)
- Panel loads proposal list from `state.radarBayReport` (already in state if Radar Bay was run this session), shows skills list at bottom, confirm-before-save flow working

### What's Next
- **Treasury** — cost tracking per agent, ROI dashboard, spend guardrails (`gx=3, gy=3`, col 4 row 4)
- Or: **Memory Room** — brain compression, ChromaDB re-indexing, cold storage (`gx=2, gy=3`, col 3 row 4)
- Or: **OpenClaw cron schedules** — War Room 7am, Radar Bay Tuesday 6am, etc.

### Gotchas for Next Session
- SKILLS_DIR is `~/.openclaw/skills/` (hardcoded, not configurable) — skills are always written here regardless of BRAIN_PATH
- Skill filenames: `<slug>_v<n>.md` — slug is slugified from proposal title (lowercase, alphanumeric + underscore, max 60 chars)
- Version is determined at generate time (not save time) — if user generates without saving and generates again, they'll get v1 twice. This is intentional: the preview shows the version, and save uses what the preview returned.
- Armory panel requires Radar Bay to have been run (either in the same session or cached in state) to show proposals. If `state.radarBayReport` is null, panel shows "RUN RADAR BAY FIRST" message.
- LLM sometimes returns non-standard frontmatter (uses `title:` instead of `name:`, adds extra fields). The content is saved as-is — the `get_skills_list()` parser handles missing `name:` gracefully by falling back to the filename.
- Vault mirror at `rooms/armory/skills/` is for Obsidian visibility only — OpenClaw reads from `~/.openclaw/skills/`

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
