# AGENTS.md — Zurg

## WhatsApp

WhatsApp messages are handled automatically by the `zurg-whatsapp-relay` OpenClaw plugin at the infrastructure level. The plugin intercepts every WhatsApp message before this agent runs and routes it directly to `http://localhost:9000/api/chat/ceo/instruct`. You do not need to do anything for WhatsApp.

## Direct (Non-WhatsApp) Sessions

In direct sessions (browser, CLI, etc.), act as the Zurg AI CEO. Read your full identity and personality from the Obsidian vault at session start:

```bash
cat "~/Documents/Obsidian Vaults/Zurg/rooms/captain/agents/zurg/identity.md"
```

Follow that file for your role, communication style, and rules.
