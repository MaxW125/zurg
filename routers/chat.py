import asyncio
import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents.ceo_room_mvp import chat_stream, run_ceo

router = APIRouter(prefix="/api/chat")

BRAIN_PATH   = os.getenv("BRAIN_PATH", "./brain")
HISTORY_FILE = os.path.join(BRAIN_PATH, "rooms", "captain", "chat_history.json")


def _load_history() -> list:
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_message(role: str, text: str, source: str = "browser"):
    history = _load_history()
    history.append({
        "role":      role,
        "text":      text,
        "source":    source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


class ChatMessage(BaseModel):
    message: str


class InstructMessage(BaseModel):
    message: str
    direction: str = ""
    brief: dict = {}
    design: dict = {}
    source: str = "browser"


@router.get("/history")
async def get_history():
    """Return the full shared chat history."""
    return _load_history()


@router.post("/ceo/stream")
async def stream_chat(body: ChatMessage):
    """Stream Zurg's conversational response back to the UI."""
    async def generator():
        async for chunk in chat_stream(body.message):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


async def _run_pipeline_background(payload: dict, source: str):
    """Run the full CEO pipeline and notify via WhatsApp when done."""
    from agents.notify import notify
    result = await run_ceo(payload)
    if result.get("response"):
        _save_message("zurg", result["response"], source=source)
        await notify(result["response"])


@router.post("/ceo/instruct")
async def instruct_ceo(body: InstructMessage, background_tasks: BackgroundTasks):
    """Give Zurg a command — he classifies intent and delegates to the right agent."""
    _save_message("owner", body.message, source=body.source)

    payload = {
        "message":   body.message,
        "direction": body.direction,
        "brief":     body.brief,
        "design":    body.design,
    }

    # For WhatsApp: return ack immediately, run pipeline in background
    if body.source == "whatsapp":
        from agents.ceo_room_mvp import _classify_intent, _load_identity
        from agents.llm_client import call_local
        intent = await _classify_intent(body.message)
        if intent == "research":
            background_tasks.add_task(_run_pipeline_background, payload, body.source)
            ack = "On it — I'll text you when the design is ready for approval."
            _save_message("zurg", ack, source=body.source)
            return {"response": ack, "intent": intent, "data": {}, "awaiting_approval": False}

    result = await run_ceo(payload)
    if result.get("response"):
        _save_message("zurg", result["response"], source=body.source)
    return result
