import os
import anthropic

CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _log_cost(room: str, model: str, tokens_in: int, tokens_out: int) -> None:
    try:
        from agents.treasury_mvp import append_cost_entry
        append_cost_entry(room, model, tokens_in, tokens_out)
    except Exception:
        pass


def _check_cap() -> None:
    try:
        from agents.treasury_mvp import check_daily_cap
        check_daily_cap()
    except RuntimeError:
        raise
    except Exception:
        pass


async def call_claude(prompt: str, system: str = "", room: str = "unknown") -> str:
    """Call Claude Sonnet. Used for structured JSON and complex reasoning tasks."""
    _check_cap()
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    kwargs = {
        "model": CLAUDE_MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    message = await client.messages.create(**kwargs)
    _log_cost(room, CLAUDE_MODEL, message.usage.input_tokens, message.usage.output_tokens)
    return message.content[0].text.strip()


async def call_claude_haiku(prompt: str, system: str = "", room: str = "unknown") -> str:
    """Call Claude Haiku. Used for simple free-text tasks."""
    _check_cap()
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    kwargs = {
        "model": CLAUDE_HAIKU_MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    message = await client.messages.create(**kwargs)
    _log_cost(room, CLAUDE_HAIKU_MODEL, message.usage.input_tokens, message.usage.output_tokens)
    return message.content[0].text.strip()


async def call_claude_stream(prompt: str, system: str = ""):
    """Streaming Claude Sonnet. Used for browser chat."""
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    kwargs = {
        "model": CLAUDE_MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text
