import os
import json
from agents.llm_client import call_local, call_claude, call_local_stream, call_claude_stream
from agents.brain import load_system_prompt

BRAIN_PATH           = os.getenv("BRAIN_PATH", "./brain")
LAST_BRIEF_FILE      = os.path.join(BRAIN_PATH, "rooms", "captain", "last_brief.json")
PIPELINE_CONFIG_FILE = os.path.join(BRAIN_PATH, "rooms", "captain", "pipeline_config.json")
LAST_DESIGN_FILE     = os.path.join(BRAIN_PATH, "rooms", "captain", "last_design.json")


def _load_pipeline_config() -> dict:
    defaults = {"auto_design": False, "auto_approval": False}
    try:
        with open(PIPELINE_CONFIG_FILE) as f:
            return {**defaults, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults


def _save_last_design(design: dict):
    os.makedirs(os.path.dirname(LAST_DESIGN_FILE), exist_ok=True)
    with open(LAST_DESIGN_FILE, "w") as f:
        json.dump(design, f, indent=2)


def _save_last_brief(brief: dict):
    os.makedirs(os.path.dirname(LAST_BRIEF_FILE), exist_ok=True)
    with open(LAST_BRIEF_FILE, "w") as f:
        json.dump(brief, f, indent=2)


def _load_last_brief() -> dict:
    try:
        with open(LAST_BRIEF_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


INTENT_SYSTEM = """You are an intent classifier. Read the message and output ONLY a JSON object: {"intent": "<value>"}

Intent rules — pick the FIRST one that matches:
- "research"  → message mentions: niche, product idea, find, discover, research, market, opportunity, what should I sell, what sells well
- "design"    → message mentions: design, image, generate image, create image, draw, illustrate, make a design, send it to the designer, designer, create designs
- "publish"   → message mentions: publish, shopify, list, post, upload, go live, put it on the store
- "pipeline"  → message mentions: full pipeline, start from scratch, do everything, run it all
- "chat"      → anything else (greetings, questions, status, yes/no, unclear)

Examples:
"find me a niche about dogs" → {"intent": "research"}
"research something related to hiking" → {"intent": "research"}
"what niche should I sell" → {"intent": "research"}
"generate a design for this" → {"intent": "design"}
"make an image for the brief" → {"intent": "design"}
"send it to the designer" → {"intent": "design"}
"publish this to shopify" → {"intent": "publish"}
"run the full pipeline" → {"intent": "pipeline"}
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
        ack = await call_claude(ack_prompt, system=identity)

    # Delegate based on intent
    data = {}
    awaiting_approval = False

    if intent == "research":
        from agents.researcher_room_mvp import run_researcher
        pipeline = _load_pipeline_config()
        # Extract the actual niche topic from the conversational message
        extract_prompt = f'Extract the niche or product topic from this message: "{message}"\nOutput only 2-5 words describing the topic. No punctuation, no explanation.'
        try:
            direction = (await call_local(extract_prompt, system="Output only the niche topic, 2-5 words max. Nothing else.")).strip()
        except Exception:
            direction = input.get("direction", message)
        data = await run_researcher({"direction": direction})
        _save_last_brief(data)

        if pipeline.get("auto_design"):
            from agents.designer_room_mvp import run_designer
            design = await run_designer(data)
            _save_last_design(design)
            data["design"] = design
            if pipeline.get("auto_approval"):
                from agents.approval_room_mvp import auto_decide
                approval = await auto_decide(design)
                data["approval"] = approval
                awaiting_approval = False
                summary_prompt = f"""Full auto pipeline complete.
Niche: {data['niche']} | Product: {data['product_type']}
Design: {design.get('image_path','unknown')}
Approval: {'APPROVED and published to Shopify' if approval.get('approved') else 'REJECTED — design discarded'}
Write 2 sentences summarising what happened."""
            else:
                awaiting_approval = True
                summary_prompt = f"""Research + Design complete.
Niche: {data['niche']} | Product: {data['product_type']}
Design saved at: {design.get('image_path','unknown')}
Write 2 sentences: what niche was found, then say the design is ready for approval."""
        else:
            summary_prompt = f"""Research complete. Brief: {json.dumps(data, indent=2)}
Write a 2-sentence summary of what the Researcher found. Report the niche and opportunity. Do NOT ask if the owner wants to do anything next — just report the result."""

        try:
            response = await call_local(summary_prompt, system=identity)
        except Exception:
            response = await call_claude(summary_prompt, system=identity)

    elif intent == "design":
        brief = input.get("brief", {}) or _load_last_brief()
        if not brief:
            response = "I need a research brief before I can design. Run research first or provide a niche direction."
        else:
            from agents.designer_room_mvp import run_designer
            data = await run_designer(brief)
            awaiting_approval = True
            summary_prompt = f"""Design complete. Image saved at: {data['image_path']}
Niche: {data['niche']} | Product: {data['product_type']}
Write 1 sentence telling the owner the design is ready and asking them to approve or reject it."""
            try:
                response = await call_local(summary_prompt, system=identity)
            except Exception:
                response = await call_claude(summary_prompt, system=identity)

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
Write 2 sentences: summarise the niche found, then tell the owner the design is ready for approval."""
        try:
            response = await call_local(summary_prompt, system=identity)
        except Exception:
            response = await call_claude(summary_prompt, system=identity)

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
Write 1 sentence confirming the product is live and sharing the admin URL."""
            try:
                response = await call_local(summary_prompt, system=identity)
            except Exception:
                response = await call_claude(summary_prompt, system=identity)

    else:
        # General chat
        try:
            response = await call_local(message, system=identity)
        except Exception:
            response = await call_claude(message, system=identity)

    return {
        "intent": intent,
        "acknowledgement": ack,
        "response": response,
        "data": data,
        "awaiting_approval": awaiting_approval,
        "model_used": model_used,
    }
