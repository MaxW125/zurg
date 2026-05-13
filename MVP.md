# Zurg MVP Specification

## What We Are Building

An autonomous print-on-demand business run by AI agents. The owner (you) talks to Zurg — the AI captain — via a pixel art game interface in the browser or via WhatsApp on your phone. Zurg manages a team of specialized agents, each living in their own room. You give Zurg high-level commands. Zurg delegates to his agents. The agents do the work.

The MVP proves the core loop works end to end: research a niche → generate a design → you approve it → publish to Shopify.

---

## MVP Rooms and Agents

| Room | Agent | Job |
|------|-------|-----|
| Captain's Room | Zurg (CEO) | Receives owner commands, delegates to agents, gives updates |
| Research Room | Researcher | Finds profitable niches and product opportunities |
| Design Room | Designer | Generates product images from research briefs |
| Factory Room | Factory Agent | Publishes approved designs to Shopify as products |

---

## The MVP Pipeline

```
Owner talks to Zurg
    → Zurg delegates to Researcher
        → Researcher finds a niche
            → Designer generates a product image
                → Owner approves or rejects the image
                    → Factory Agent publishes to Shopify
```

That's it. Everything else comes later.

---

## Tech Stack

| Layer | MVP Choice | Future Swap |
|-------|-----------|-------------|
| LLM (dev) | Ollama llama3.2 (free, local) | Claude Sonnet (production) |
| LLM (production) | Claude Sonnet via Anthropic API | — |
| Image generation | Google Imagen (Gemini API) | Ideogram, Flux |
| Storefront | Shopify (custom app, shpat_ token) | — |
| Messaging | OpenClaw → WhatsApp | — |
| Memory/Brain | Flat markdown files, path from `BRAIN_PATH` env var | Obsidian vault |
| Secrets | Environment variables | HashiCorp Vault |
| Vector DB | None (MVP) | ChromaDB |
| Scheduling | None (MVP, manual triggers) | OpenClaw cron |

---

## Agent Pattern (Follow This Every Time)

Every MVP agent must follow this pattern. No exceptions.

```python
# agents/[name]_room_mvp.py

from agents.llm_client import call_local, call_claude
import os

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")  # never hardcode

async def run_[name](input: dict) -> dict:
    # 1. Build prompt
    # 2. Call Ollama first, fall back to Claude
    try:
        result = await call_local(prompt, system)
    except Exception:
        result = await call_claude(prompt, system)
    # 3. Return structured result
    # 4. Optionally write to BRAIN_PATH
```

---

## UI

- Pixel art JRPG top-down view
- Each room is a PNG image
- Each agent is a sprite that wanders their room
- Click an agent → their panel slides up
- Zurg's panel = CEO chat (talk to him directly)
- Other panels = show that agent's output
- Owner approval step = a panel that shows the design image with Approve / Reject buttons
- Press Start 2P font, scanlines, dark purple theme

---

## API Endpoints (MVP Only)

```
POST /api/chat/ceo/stream         — talk to Zurg (streaming)
POST /api/chat/ceo/instruct       — give Zurg a command (he delegates)
POST /api/rooms/research/run      — trigger Research Room
POST /api/rooms/design/run        — trigger Design Room
POST /api/rooms/factory/run       — trigger Factory Room (publish to Shopify)
POST /api/approval/decide         — owner approves or rejects a design
GET  /health                      — health check
```

---

## Environment Variables (MVP)

```bash
ANTHROPIC_API_KEY     # optional in dev, required in production
GOOGLE_API_KEY        # for Imagen image generation
SHOPIFY_ACCESS_TOKEN  # shpat_... token from Shopify custom app
SHOPIFY_STORE_URL     # yourstore.myshopify.com
BRAIN_PATH            # path to brain folder (default: ./brain)
OLLAMA_HOST           # default: http://host.docker.internal:11434
```

---

## Hard Rules

1. **Shopify only** — no Etsy references anywhere in the codebase
2. **Ollama first** — every agent tries Ollama before hitting the Anthropic API
3. **`BRAIN_PATH` env var** — never hardcode brain file paths
4. **One agent at a time** — build it, verify it works, then build the next
5. **No Vault for MVP** — all secrets in env vars
6. **No ChromaDB for MVP** — flat markdown files only
7. **OpenClaw is untouched** — don't modify openclaw/ config unless specifically working on messaging
8. **Approval gate is mandatory** — no design goes to Factory without owner approval

---

## Definition of Done (MVP)

- [ ] Owner can talk to Zurg via browser chat
- [ ] Owner can talk to Zurg via WhatsApp (OpenClaw)
- [ ] Zurg delegates a research task to the Researcher
- [ ] Researcher returns a niche brief
- [ ] Designer generates a product image from the brief
- [ ] Owner sees the image and clicks Approve or Reject
- [ ] Factory Agent publishes an approved design to Shopify as a real product
- [ ] All four rooms visible on the pixel art map with wandering sprites
- [ ] System runs on Ollama with zero Anthropic API calls in dev mode

---

## What Is Explicitly Out of Scope for MVP

- ChromaDB / vector search
- HashiCorp Vault
- OpenClaw cron scheduling (manual triggers only)
- Obsidian vault integration
- Everbee market data (use mock data)
- TikTok / social media posting
- Analytics, pricing, shop health agents
- Radar Bay, Armory, War Room
- Bootstrap wizard
- Full brain RAG system
- Multi-agent autonomous operation (MVP is human-in-the-loop)
