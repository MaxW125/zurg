import os
import httpx
import anthropic

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = "llama3.2"
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _log_cost(room: str, model: str, tokens_in: int, tokens_out: int) -> None:
    try:
        from agents.treasury_mvp import append_cost_entry
        append_cost_entry(room, model, tokens_in, tokens_out)
    except Exception:
        pass  # never let cost logging crash an agent


def _check_cap() -> None:
    try:
        from agents.treasury_mvp import check_daily_cap
        check_daily_cap()
    except RuntimeError:
        raise  # let the cap breach bubble up so callers fall back to Ollama
    except Exception:
        pass  # import errors or file errors shouldn't block Claude calls


async def call_local(prompt: str, system: str = "") -> str:
    """Call Ollama (llama3.2). Raises on failure so callers can fall back to Claude.
    Set OLLAMA_ENABLED=false in .env to skip Ollama entirely and always use Claude."""
    if os.getenv("OLLAMA_ENABLED", "true").lower() == "false":
        raise RuntimeError("Ollama disabled — using Claude")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False, "options": {"num_ctx": 8192}},
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


async def call_claude(prompt: str, system: str = "", room: str = "unknown") -> str:
    """Call Claude Sonnet. Used as fallback for complex/JSON tasks."""
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
    """Call Claude Haiku. Used as fallback for simple/free-text tasks."""
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


async def call_local_stream(prompt: str, system: str = ""):
    """Streaming version of call_local. Yields text chunks.
    Set OLLAMA_ENABLED=false to skip and fall back to call_claude_stream."""
    if os.getenv("OLLAMA_ENABLED", "true").lower() == "false":
        raise RuntimeError("Ollama disabled — using Claude")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_HOST}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": True},
        ) as r:
            r.raise_for_status()
            import json
            async for line in r.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        break


async def call_claude_stream(prompt: str, system: str = ""):
    """Streaming version of call_claude. Yields text chunks."""
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
