import os
import json
from agents.llm_client import call_local, call_claude_haiku, call_local_stream, call_claude_stream
from agents.brain import load_system_prompt

BRAIN_PATH      = os.getenv("BRAIN_PATH", "./brain")
LAST_BRIEF_FILE  = os.path.join(BRAIN_PATH, "rooms", "captain", "last_brief.json")
LAST_DESIGN_FILE = os.path.join(BRAIN_PATH, "rooms", "captain", "last_design.json")


def _save_last_brief(brief: dict):
    os.makedirs(os.path.dirname(LAST_BRIEF_FILE), exist_ok=True)
    with open(LAST_BRIEF_FILE, "w") as f:
        json.dump(brief, f, indent=2)


def _save_last_design(design: dict):
    os.makedirs(os.path.dirname(LAST_DESIGN_FILE), exist_ok=True)
    with open(LAST_DESIGN_FILE, "w") as f:
        json.dump(design, f, indent=2)

INTENT_SYSTEM = """You are an intent classifier. Read the message and output ONLY a JSON object: {"intent": "<value>"}

Intent rules — pick the FIRST one that matches:
- "research"       → message mentions: niche, product idea, find, discover, research, market, opportunity, what should I sell, what sells well
- "design"         → message mentions: design, image, generate image, create image, draw, illustrate, make a design
- "publish"        → message mentions: publish, shopify, list, post, upload, go live, put it on the store
- "pipeline"       → message mentions: full pipeline, start from scratch, do everything, run it all
- "set_reporting"  → message mentions: weekly report, daily report, switch to weekly, go weekly, switch to daily, daily briefing, weekly briefing, report frequency, weekly updates, daily updates
- "chat"           → anything else (greetings, questions, status, yes/no, unclear)

Examples:
"find me a niche about dogs" → {"intent": "research"}
"research something related to hiking" → {"intent": "research"}
"what niche should I sell" → {"intent": "research"}
"generate a design for this" → {"intent": "design"}
"make an image for the brief" → {"intent": "design"}
"publish this to shopify" → {"intent": "publish"}
"run the full pipeline" → {"intent": "pipeline"}
"switch to weekly reports" → {"intent": "set_reporting"}
"go back to daily" → {"intent": "set_reporting"}
"how are you" → {"intent": "chat"}
"yes" → {"intent": "chat"}

Output ONLY raw JSON. No explanation."""


def _load_identity() -> str:
    fallback = "You are Zurg, the AI CEO of a print-on-demand business. Be direct and helpful."
    return load_system_prompt("captain", "zurg", fallback)


async def _classify_intent(message: str) -> str:
    """Use Ollama to classify the owner's intent. Falls back to 'chat' on failure."""
    try:
        raw = await call_local(message, system=INTENT_SYSTEM)
        data = json.loads(raw)
        return data.get("intent", "chat")
    except Exception:
        return "chat"


async def chat_stream(message: str):
    """
    Stream Zurg's conversational response to the owner.
    Used by POST /api/chat/ceo/stream
    Yields text chunks.
    """
    identity = _load_identity()
    try:
        async for chunk in call_local_stream(message, system=identity):
            yield chunk
    except Exception:
        async for chunk in call_claude_stream(message, system=identity):
            yield chunk


async def run_ceo(input: dict) -> dict:
    """
    Receive a command from the owner, classify intent, delegate to the right agent.
    Used by POST /api/chat/ceo/instruct

    Input keys:
      - message: str — the owner's command
      - brief: dict (optional) — pass an existing research brief to skip research
      - design: dict (optional) — pass an existing design to skip design

    Returns:
      - intent: what Zurg understood
      - response: Zurg's message back to the owner
      - data: the agent result (brief, design, or product)
      - awaiting_approval: True if a design is ready and needs owner sign-off
    """
    identity = _load_identity()
    message = input.get("message", "")
    intent = await _classify_intent(message)

    # Build Zurg's acknowledgement before delegating
    ack_prompt = f"""The owner said: "{message}"
You understood their intent as: {intent}
Write a short 1-sentence acknowledgement of what you're about to do."""

    model_used = "ollama"
    try:
        ack = await call_local(ack_prompt, system=identity)
    except Exception:
        model_used = "claude"
        ack = await call_claude_haiku(ack_prompt, system=identity, room="ceo")

    # Delegate based on intent
    data = {}
    awaiting_approval = False

    if intent == "research":
        from agents.researcher_room_mvp import run_researcher
        # Extract the actual niche topic from the conversational message
        extract_prompt = f'Extract the niche or product topic from this message: "{message}"\nOutput only 2-5 words describing the topic. No punctuation, no explanation.'
        try:
            direction = (await call_local(extract_prompt, system="Output only the niche topic, 2-5 words max. Nothing else.")).strip()
        except Exception:
            direction = input.get("direction", message)

        data = await run_researcher({"direction": direction})
        _save_last_brief(data)

        from agents.designer_room_mvp import run_designer
        design = await run_designer(data)
        _save_last_design(design)
        data["design"] = design
        awaiting_approval = True

        response = "Design is ready — open the Approval Room to approve or deny."

    elif intent == "design":
        brief = input.get("brief", {})
        if not brief:
            response = "I need a research brief before I can design. Run research first or provide a niche direction."
        else:
            from agents.designer_room_mvp import run_designer
            data = await run_designer(brief)
            awaiting_approval = True
            summary_prompt = f"""Design complete. Image saved at: {data['image_path']}
Niche: {data['niche']} | Product: {data['product_type']}
Write 1 sentence telling the owner the design is ready and asking them to approve or reject it. You are the CEO — the Designer agent did this work, not you."""
            try:
                response = await call_local(summary_prompt, system=identity)
            except Exception:
                response = await call_claude_haiku(summary_prompt, system=identity, room="ceo")

    elif intent == "pipeline":
        from agents.researcher_room_mvp import run_researcher
        from agents.designer_room_mvp import run_designer
        direction = input.get("direction", message)
        brief = await run_researcher({"direction": direction})
        _save_last_brief(brief)
        data = await run_designer(brief)
        data["brief"] = brief
        awaiting_approval = True
        summary_prompt = f"""Full pipeline complete.
Niche: {brief['niche']} | Product: {brief['product_type']}
Design saved at: {data['image_path']}
Write 2 sentences: summarise the niche the Researcher found, then tell the owner the Designer has a design ready for approval. You are the CEO — speak as the boss who delegated, not the one who did the work."""
        try:
            response = await call_local(summary_prompt, system=identity)
        except Exception:
            response = await call_claude_haiku(summary_prompt, system=identity, room="ceo")

    elif intent == "publish":
        design = input.get("design", {})
        if not design:
            response = "Nothing to publish yet. I need an approved design first."
        else:
            from agents.factory_room_mvp import run_factory
            data = await run_factory(design)
            summary_prompt = f"""Product published to Shopify.
Title: {data['title']}
URL: {data['product_url']}
Write 1 sentence confirming the Factory agent got the product live and share the admin URL. You are the CEO — speak as the boss who delegated, not the one who did the work."""
            try:
                response = await call_local(summary_prompt, system=identity)
            except Exception:
                response = await call_claude_haiku(summary_prompt, system=identity, room="ceo")

    elif intent == "set_reporting":
        mode = "weekly" if any(w in message.lower() for w in ["weekly", "week"]) else "daily"
        config_path = os.path.join(BRAIN_PATH, "rooms", "captain", "reporting_config.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            json.dump({"mode": mode}, f)
        confirm_prompt = f'You just switched the owner\'s briefing mode to "{mode}" reports. Write 1 sentence confirming this change in your own voice.'
        try:
            response = await call_local(confirm_prompt, system=identity)
        except Exception:
            response = await call_claude_haiku(confirm_prompt, system=identity, room="ceo")

    else:
        # General chat
        try:
            response = await call_local(message, system=identity)
        except Exception:
            response = await call_claude_haiku(message, system=identity, room="ceo")

    return {
        "intent": intent,
        "acknowledgement": ack,
        "response": response,
        "data": data,
        "awaiting_approval": awaiting_approval,
        "model_used": model_used,
    }
