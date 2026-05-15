"""
Owner notification via WhatsApp (OpenClaw).

Usage:
    from agents.notify import notify

    await notify("Design approved: Axolotl Lovers Hoodie → Shopify ✓")

Falls back silently if OpenClaw is unavailable or WhatsApp isn't linked.
"""

import asyncio
import os
import shutil

OWNER_NUMBER = os.getenv("OWNER_PHONE", "")


def _send_sync(message: str) -> bool:
    """Synchronous send via OpenClaw CLI. Returns True on success."""
    openclaw = shutil.which("openclaw")
    if not openclaw:
        print("[notify] openclaw not found in PATH — skipping WhatsApp notification")
        return False

    import subprocess
    try:
        result = subprocess.run(
            [
                openclaw, "message", "broadcast",
                "--channel", "whatsapp",
                "--account", "zurg",
                "--targets", OWNER_NUMBER,
                "--message", message,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True
        print(f"[notify] WhatsApp send failed: {result.stderr.strip()[:200]}")
        return False
    except Exception as e:
        print(f"[notify] WhatsApp send error: {e}")
        return False


async def notify(message: str) -> bool:
    """Send a WhatsApp message to the owner. Non-blocking, never raises."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send_sync, message)
