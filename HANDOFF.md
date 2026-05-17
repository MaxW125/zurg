# Handoff — Session Notes

_Update this before ending a session or starting a new room. One section per session, most recent at top._

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
