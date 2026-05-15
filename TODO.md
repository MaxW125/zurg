# Zurg — TODO

## Done
- [x] Core pipeline: research → design → approval → Shopify
- [x] Pixel art UI with 16-room grid (4×4 map, 4 built rooms)
- [x] Approval Room with agent + auto/manual toggle + verdict storage
- [x] Printify integration (mockup generation, flat design fallback)
- [x] Designer background removal via rembg (real PNG transparency)
- [x] Ollama dev mode (zero Anthropic charges during development)
- [x] Shared chat memory across browser and WhatsApp
- [x] OpenClaw WhatsApp routing wired up (disabled until real SIM)
- [x] Approval Room — agent + auto/manual toggle + verdict storage + phase 1/2/3 thresholds
- [x] Printify integration — mockup generation with correct shirt color (black default)
- [x] rembg background removal — real PNG transparency on all generated designs
- [x] Product catalog — T-Shirt, Hoodie, Long Sleeve mapped to Printify blueprints
- [x] Full auto pipeline — per-room auto toggles chain research → design → approval → Shopify
- [x] 4×4 map expansion — 16 room grid with 11 placeholder rooms
- [x] Autonomous researcher loop — configurable daily cap, delay, live DDG market data, auto-triggers designer

---

## Up Next

### Quick Wins
- [ ] Factory room background image — pixel art PNG to replace 🏭 emoji placeholder
- [ ] Run 20+ design cycles to build verdict history for Approval Agent learning

### Agent Rooms (build one at a time)
> Finish each room as completely as possible before moving to the next. Room background images and agent sprites can be skipped.

- [ ] Analytics Room — weekly Shopify revenue reports, top niches, trend detection
- [ ] Pricing Room — competitor price monitoring, dynamic repricing, margin protection
- [ ] CS Room — handle Shopify customer messages, order issues, review requests
- [ ] Shop Health Room — listing SEO refresh, stale listing detection
- [ ] Media Bay — TikTok/Instagram content creation, Publer scheduling
- [ ] Monitoring Room — system health alerts, spend warnings, API failure detection
- [ ] War Room — daily 7am synthesis ritual, consensus action plan across all rooms
- [ ] Radar Bay — proposes system improvements, monitors agent performance
- [ ] Armory — converts proposals into SKILL.md files in OpenClaw workspace
- [ ] Memory Room — brain compression, ChromaDB re-indexing, cold storage
- [ ] Treasury — cost tracking per agent, ROI dashboard, spend guardrails

### Automation
- [ ] OpenClaw cron schedules — War Room 7am, CEO 8am, Analytics Sunday 11pm, Pricing Monday 6am, Shop Health Wednesday 6am, Radar Tuesday 6am
- [ ] Event-driven sprite movement — characters react to pipeline events via SSE

### Approval Engine
- [ ] Phase 2 — agent predicts verdict, owner spot-checks (unlock after ~100 verdicts, >85% accuracy)
- [ ] Phase 3 — fully autonomous approvals with 7-day audit window (unlock after ~200 verdicts)

### Infrastructure
- [ ] Wire Everbee real market data into Researcher — code complete, awaiting Everbee Open API approval
- [ ] Look into better research methods (custom Etsy scraper, alternative data sources)
- [ ] LLM audit — pick the best model for each agent (researcher, designer prompt, approval, etc.)
- [ ] Swap flat brain → ChromaDB-indexed Obsidian vault
- [ ] Swap .env secrets → HashiCorp Vault
- [ ] Staging environment with test-mode flags

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
