# Zurg

Zurg is a set of AI agents that run a print-on-demand store. I wanted to see how much of a small online business could run on its own if I only stepped in to approve things.

Each agent has its own "room" in a pixel-art command center you can pan around in the browser. Zurg is the CEO agent. You talk to it in the browser or over WhatsApp, and it hands work off to the rest of the team.

## How it works

1. **Researcher** looks at Etsy listings, Google Trends and seasonal timing to pick a niche and write a product brief.
2. **Designer** turns the brief into artwork with Google Imagen.
3. **Approval** sends the design to my phone over WhatsApp. I approve it, or deny it with feedback and it gets redesigned.
4. **Factory** creates the product in Printify, generates mockups, and publishes it to Shopify and Etsy.

Around that pipeline there are rooms for analytics, pricing, customer service, shop health, monitoring, social media, memory and cost tracking (Treasury). Every night each room writes a report, the War Room combines them into an action plan, and I get a briefing on WhatsApp at 8am.

## Stack

- **Backend:** Python, FastAPI
- **LLMs:** Claude API (Haiku for simple agents, Sonnet for the heavier ones), Ollama for free local dev
- **Images:** Google Imagen 4
- **Commerce:** Printify, Shopify Admin API, Etsy Open API v3
- **Messaging:** WhatsApp through OpenClaw
- **Frontend:** plain HTML/CSS/JS canvas map
- **Memory:** markdown files in a `brain/` folder (works as an Obsidian vault)

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn main:app --port 9000
```

Then open http://localhost:9000.

For dev you only need `BRAIN_PATH` and a local Ollama running. Everything routes through Ollama, so no API calls cost anything. The full pipeline needs the Anthropic, Google, Printify, Shopify and Etsy keys in `.env.example`.

`cron_runner.py` handles the scheduled jobs (nightly reports, War Room, morning briefing). I run it with cron on a Mac mini.

## Docs

- `MVP.md` covers the first working version.
- `FINAL_VISION.md` is the full plan for every room.
- `HANDOFF.md` is a running log of what changed and why.
- `TODO.md` is what's left.
