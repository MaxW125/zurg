import os

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")


def load_system_prompt(room: str, agent: str, fallback: str = "") -> str:
    """
    Load room.md + agent identity.md from the Obsidian vault and combine them
    into a single system prompt. Either file can be missing — the other still loads.
    Falls back to `fallback` if neither file exists.

    Inject dynamic values after calling this:
        prompt = load_system_prompt("research", "researcher", FALLBACK)
        prompt = prompt.replace("{PRODUCT_TYPES}", "...")
    """
    brain_path = os.getenv("BRAIN_PATH", BRAIN_PATH)
    room_path     = os.path.join(brain_path, "rooms", room, "room.md")
    identity_path = os.path.join(brain_path, "rooms", room, "agents", agent, "identity.md")

    parts = []
    for path in (room_path, identity_path):
        try:
            with open(path) as f:
                content = f.read().strip()
                if content:
                    parts.append(content)
        except FileNotFoundError:
            pass

    return "\n\n---\n\n".join(parts) if parts else fallback


def load_prompt(room: str, agent: str, fallback: str = "") -> str:
    """
    Load an agent's user-facing prompt template from the Obsidian vault.
    File lives at: $BRAIN_PATH/rooms/{room}/agents/{agent}/prompt.md

    Use {PLACEHOLDERS} in the file for dynamic values, then call .replace() after:
        template = load_prompt("design", "copywriter", FALLBACK)
        prompt = template.replace("{NICHE}", niche).replace("{PRODUCT_TYPE}", product_type)

    Falls back to `fallback` if the file is missing.
    """
    brain_path = os.getenv("BRAIN_PATH", BRAIN_PATH)
    prompt_path = os.path.join(brain_path, "rooms", room, "agents", agent, "prompt.md")
    try:
        with open(prompt_path) as f:
            content = f.read().strip()
            if content:
                return content
    except FileNotFoundError:
        pass
    return fallback
