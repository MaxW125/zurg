import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents.ceo_room_mvp import chat_stream, run_ceo

router = APIRouter(prefix="/api/chat")

BRAIN_PATH   = os.getenv("BRAIN_PATH", "./brain")
HISTORY_FILE = os.path.join(BRAIN_PATH, "hot", "chat_history.json")


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


@router.post("/ceo/instruct")
async def instruct_ceo(body: InstructMessage):
    """Give Zurg a command — he classifies intent and delegates to the right agent."""
    _save_message("owner", body.message, source=body.source)

    result = await run_ceo({
        "message":   body.message,
        "direction": body.direction,
        "brief":     body.brief,
        "design":    body.design,
    })

    if result.get("response"):
        _save_message("zurg", result["response"], source=body.source)

    return result
