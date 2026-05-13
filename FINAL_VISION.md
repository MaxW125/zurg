# Zurg — Final Vision

## What This Becomes

A fully autonomous AI-powered print-on-demand business that runs itself. The owner checks in occasionally, approves designs early on, and watches revenue grow. Over time the agents earn the right to operate without human approval on every decision. The system gets smarter the longer it runs.

---

## Current State (MVP Complete)

The core pipeline is live and working end-to-end.

**What's built:**
- Pixel art JRPG-style command center (browser UI) with 4 rooms on a pannable/zoomable 2048×2048 map
- Character sprites with circular wandering paths and cross-room visiting via grid corridors
- Shooting stars, space background, scanlines — full aesthetic
- Zurg (CEO) chat — browser UI and WhatsApp both route through the same FastAPI pipeline
- Shared chat history persisted to `brain/hot/chat_history.json` — cross-interface memory works
- Researcher agent — niche brief generation via Ollama → Claude fallback
- Designer agent — image generation via Google Imagen 4 Fast
- Factory agent — Shopify draft product creation with image upload
- Approval gate — owner approves/rejects before anything hits Shopify
- Full Ollama dev mode — zero Anthropic API calls during development

**What's pending:**
- WhatsApp on a real SIM (Google Voice doesn't work with WhatsApp — need a prepaid SIM)
- Background images for rooms that don't have them yet (Factory room uses emoji placeholder)
- Design feedback loop (teach Zurg what good/bad looks like — build after 10–20 design cycles)

**Current tech in use:**
- LLM (dev): Ollama llama3.2 (local, free)
- LLM (prod fallback): Claude Sonnet 4.6 (claude-sonnet-4-6)
- Image generation: Google Imagen 4 Fast (imagen-4.0-fast-generate-001)
- Storefront: Shopify Admin REST API 2025-01 (shpat_ token, expires 24hrs)
- Messaging: OpenClaw → WhatsApp (disabled in dev, re-enable when real SIM is ready)
- Brain: flat markdown in `brain/hot/` and `brain/warm/`
- Server: FastAPI on port 9000 (port 8000 reserved for OpenClaw)

---

## The Full Agent Company

| Room | Agent | Status | Job |
|------|-------|--------|-----|
| Captain's Room | Zurg (CEO) | ✅ Built | Strategic decisions, War Room synthesis, delegates to all agents |
| Research Room | Researcher | ✅ Built | Competitor analysis, niche discovery, keyword research via Everbee |
| Design Room | Designer | ✅ Built | Generates designs via Imagen/Ideogram, manages design queue |
| Factory Room | Factory Agent | ✅ Built | Printify product creation, Shopify publishing, fulfillment monitoring |
| Approval Room | Approval Agent | 🔲 Not built | Learns owner taste, predicts approvals, earns autonomous authority |
| Customer Service Room | CS Agent | 🔲 Not built | Handles Shopify customer messages, order issues, review requests |
| Analytics Room | Analyst | 🔲 Not built | Weekly performance reports, revenue tracking, trend detection |
| Pricing Room | Pricing Agent | 🔲 Not built | Competitor price monitoring, dynamic repricing, margin protection |
| Shop Health Room | Shop Agent | 🔲 Not built | Listing health, SEO refresh, stale listing detection |
| Media Bay | Media Agent | 🔲 Not built | TikTok/Instagram content creation, Publer scheduling |
| Monitoring Room | Monitor | 🔲 Not built | System health alerts, spend warnings, API failure detection |
| Radar Bay | Radar Agent | 🔲 Not built | Proposes system improvements, monitors agent performance |
| Armory | Armory Agent | 🔲 Not built | Builds and stores new agent skills as SKILL.md files |
| War Room | (all agents) | 🔲 Not built | Daily 7am synthesis ritual, consensus action plan |
| Memory Room | Memory Agent | 🔲 Not built | Brain compression, ChromaDB re-indexing, cold storage |
| Treasury | (service) | 🔲 Not built | Cost tracking per agent, ROI dashboard, spend guardrails |

---

## The Full Autonomous Pipeline

```
War Room (7am daily)
    → Synthesizes all room statuses
        → CEO Room (8am daily)
            → Reads War Room output
                → Issues instructions to all rooms

Research Room (on CEO instruction, max 2x/day)
    → Everbee competitor analysis
        → Niche scoring and brief generation
            → Design Room
                → Image prompt generation
                    → Imagen/Ideogram API
                        → Compliance check
                            → Approval Room
                                → Phase 1: Owner reviews every design
                                → Phase 2: Agent predicts, owner spot-checks
                                → Phase 3: Agent approves autonomously (>85% accuracy)
                                    → Factory Room
                                        → Printify product creation
                                            → Shopify publish
                                                → Media Bay
                                                    → Social content creation
                                                        → Publer scheduling
```

---

## Tech Stack (Full System)

| Layer | Dev (Now) | Production (Target) |
|-------|-----------|---------------------|
| LLM (complex) | Ollama llama3.2 | Claude Sonnet 4.6 |
| LLM (simple) | Ollama llama3.2 | Claude Haiku 4.5 |
| Image generation | Google Imagen 4 Fast | Imagen primary, Ideogram fallback, Flux backup |
| Storefront | Shopify REST API 2025-01 | Same |
| Fulfillment | Not wired yet | Printify (primary), Gelato (fallback) |
| Messaging | OpenClaw (disabled) | OpenClaw → WhatsApp, Telegram, iMessage |
| Memory/Brain | Flat markdown (brain/) | ChromaDB-indexed Obsidian vault |
| Vector DB | None | ChromaDB (excludes /brain/customers/) |
| Secrets | .env file | HashiCorp Vault |
| Scheduling | Manual triggers | OpenClaw cron |
| Agent skills | None yet | OpenClaw SKILL.md workspace |
| Analytics | None yet | Everbee + Shopify API |
| Social posting | None yet | Publer |
| Reviews | None yet | Judge.me or Yotpo |

---

## Brain Architecture

```
/brain (BRAIN_PATH — points to Obsidian vault in production)
    /hot          ← Always in context: identity, shopify token, chat history
        identity.md           — Zurg's personality and rules
        shopify-token.md      — Token refresh instructions (expires 24hrs)
        chat_history.json     — Shared message log (browser + WhatsApp)
    /warm         ← Research briefs, generated design records
        brief_TIMESTAMP_slug.md  — Niche research outputs
    /cold         ← Archived: old research, completed campaigns
    /customers    ← PII-isolated: NEVER git-tracked, NEVER ChromaDB-indexed
    /war-room     ← Daily synthesis logs
    /armory       ← Skill index
    /radar        ← System health proposals
    /bootstrap    ← First-run record
```

---

## UI Architecture

- 2048×2048 pixel art map, 4 rooms in a 2×2 grid (each 1024×1024)
- Zoom/pan with mouse wheel and drag — min scale 0.2, max 0.755
- Character sprites wander circular paths (radius 260px) centered on each room
- Cross-room visiting: characters arc to a cardinal exit, walk grid corridors, circle in destination room
- Clicking a character/icon slides up their control panel from the bottom
- Press Start 2P font, dark purple theme, CRT scanlines, shooting stars
- Space background tiles across the full viewport including void areas

**Room grid positions (2048×2048 map coords):**
- CEO (top-left): center (512, 512)
- Research (top-right): center (1536, 512)
- Design (bottom-left): center (512, 1536)
- Factory (bottom-right): center (1536, 1536)

**Assets needed (not yet created):**
- Factory room background image (currently using 🏭 emoji placeholder)
- Room background images for all future rooms

---

## Approval Engine (Three Phases)

The system is designed to earn trust over time.

**Phase 1 — Cold Start (0–20 verdicts)** ← We are here
- Every design goes to the owner for approval
- Maximum 6 designs generated until 20 verdicts collected
- Agent observes and learns taste patterns

**Phase 2 — Assisted (20–200 verdicts, >85% prediction accuracy)**
- Agent predicts owner verdict
- Owner spot-checks; can override at any time
- Agent flags low-confidence designs for human review

**Phase 3 — Autonomous (>200 verdicts, sustained >85% accuracy)**
- Agent approves designs autonomously
- All decisions logged and auditable for 7 days
- Owner can override any decision within the window
- Accuracy drops below 80% → automatic downgrade to Phase 2

Thresholds are config-file driven — never hardcoded.

---

## Self-Improvement Layer

**Radar Bay** — monitors every room's performance metrics weekly. Proposes improvements as numbered proposals. CEO reviews and approves. Armory implements.

**Armory** — converts approved proposals into SKILL.md files stored in the OpenClaw workspace. Skills are versioned, never deleted. Rollback = reactivate previous version.

**War Room** — daily 7am ritual. Every room reports status. CEO synthesizes into a consensus action plan. CEO's 8am decision cycle uses War Room output as primary context.

---

## OpenClaw Integration (Full)

OpenClaw serves three roles:

1. **Owner messaging** — WhatsApp, Telegram, iMessage. Owner receives alerts and sends commands from their phone. All messages route through `/api/chat/ceo/instruct` — same pipeline as browser.

2. **Cron scheduler** — All room schedules registered as OpenClaw cron jobs. War Room 7am, CEO 8am, Analytics Sunday 11pm, Pricing Monday 6am, Shop Health Wednesday 6am, Radar Bay Tuesday 6am.

3. **Skill storage** — Armory writes SKILL.md files to OpenClaw workspace. Owner chat sessions get skills injected automatically.

**Current status:** Wired up, routing works, WhatsApp disabled until real SIM available. Re-enable: set `"enabled": true` in `~/.openclaw/openclaw.json` → `channels.whatsapp`, restart gateway.

---

## Security and Operations

- All secrets in HashiCorp Vault — zero keys in code, config, or logs
- Spend guardrails wrap every Claude API call — rooms pause at daily limit
- `/brain/customers/` gitignored and ChromaDB-excluded always
- Bootstrap Mode runs exactly once and locks itself
- Staging environment mirrors production with test-mode flags
- All room activity logged to monitoring feed

---

## Upgrade Path from MVP

- [x] Core pipeline: research → design → approval → Shopify
- [x] Pixel art UI with 4 rooms, sprites, zoom/pan
- [x] Ollama dev mode (zero Anthropic charges)
- [x] Shared memory across browser and WhatsApp
- [x] OpenClaw WhatsApp routing wired up
- [ ] Real SIM for Zurg's WhatsApp number
- [ ] Factory room background image
- [ ] Printify integration (mockups + fulfillment)
- [ ] Design feedback loop (after 10–20 design cycles)
- [ ] Add remaining agent rooms one at a time (see table above)
- [ ] Event-driven character movement (characters react to pipeline events)
- [ ] OpenClaw cron schedules for autonomous operation
- [ ] Swap flat brain → ChromaDB-indexed Obsidian vault
- [ ] Swap .env secrets → HashiCorp Vault
- [ ] Enable Approval Engine Phase 2
- [ ] Wire Everbee real market data
- [ ] Add Radar Bay and Armory for self-improvement
- [ ] Enable War Room daily ritual
- [ ] Enable War Room daily ritual
- [ ] Treasury cost tracking per agent

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
- [ ] Bootstrap wizard runs once and locks
- [ ] Treasury showing real cost breakdown per agent
- [ ] Radar Bay generating improvement proposals
- [ ] Armory storing at least one self-generated skill
