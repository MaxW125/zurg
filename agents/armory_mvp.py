import os
import json
import re
from datetime import datetime
from agents.llm_client import call_local, call_claude
from agents.brain import load_system_prompt

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")
SKILLS_DIR = os.path.expanduser("~/.openclaw/skills")
ARMORY_DIR = os.path.join(BRAIN_PATH, "rooms", "armory", "reports")

_ARMORY_FALLBACK = """You are the Armory Agent for a print-on-demand AI business run by Zurg (CEO).
Your job is to convert a Radar Bay improvement proposal into a precise, actionable SKILL.md file.
A skill is a reusable set of step-by-step instructions that an AI agent can follow to accomplish a recurring task.

Rules:
- Be concrete: every step must be an action (check X, call Y, write Z), not an observation.
- The trigger condition must be a testable, specific state (e.g. "When analytics shows <10 products", not "When things are slow").
- Steps must be numbered and each under 20 words.
- Success criteria must be measurable (a count, a status, a file present).
- Notes: any caveats, edge cases, or gotchas.
- Output ONLY the SKILL.md content — no preamble, no explanation, nothing else.

Output format (include the frontmatter exactly):
---
name: <skill_name_in_snake_case>
version: {version}
description: <one-line description under 15 words>
trigger: <one-line specific trigger condition>
priority: P{priority}
source_proposal: {proposal_id}
created: {created}
---

## Trigger Condition
<1-2 sentences expanding on when and why this skill activates>

## Steps
1. <action step>
2. <action step>
3. <action step>
...

## Success Criteria
<measurable outcome that confirms the skill ran correctly>

## Notes
<caveats, edge cases, dependencies>"""


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:60]


def _get_next_version(slug: str) -> int:
    if not os.path.exists(SKILLS_DIR):
        return 1
    pattern = re.compile(rf"^{re.escape(slug)}_v(\d+)\.md$")
    versions = []
    for fname in os.listdir(SKILLS_DIR):
        m = pattern.match(fname)
        if m:
            versions.append(int(m.group(1)))
    return (max(versions) + 1) if versions else 1


def _load_radar_report() -> dict | None:
    path = os.path.join(BRAIN_PATH, "rooms", "radar_bay", "reports", "latest_report.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def get_skills_list() -> list[dict]:
    if not os.path.exists(SKILLS_DIR):
        return []
    skills = []
    for fname in sorted(os.listdir(SKILLS_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(SKILLS_DIR, fname)
        mtime = os.path.getmtime(fpath)
        created = datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        # Parse frontmatter for name/version/description
        name = fname.replace(".md", "")
        description = ""
        version = ""
        try:
            with open(fpath) as f:
                content = f.read()
            fm = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm:
                for line in fm.group(1).splitlines():
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("version:"):
                        version = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
        except Exception:
            pass
        skills.append({
            "filename": fname,
            "name": name,
            "version": version,
            "description": description,
            "created": created,
        })
    return skills


async def generate_skill(proposal_id: int) -> dict:
    radar_report = _load_radar_report()
    if not radar_report:
        return {"error": "No Radar Bay report found. Run Radar Bay first."}

    proposals = radar_report.get("proposals", [])
    proposal = next((p for p in proposals if p.get("id") == proposal_id), None)
    if not proposal:
        return {"error": f"Proposal #{proposal_id} not found in latest Radar Bay report."}

    title = proposal.get("title", "untitled")
    slug = _slugify(title)
    version = _get_next_version(slug)
    priority = proposal.get("priority", 3)
    created = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    system_template = _ARMORY_FALLBACK.format(
        version=version,
        priority=priority,
        proposal_id=proposal_id,
        created=created,
    )
    system = load_system_prompt("armory", "armory", system_template)

    prompt = f"""Convert this Radar Bay proposal into a SKILL.md file.

Proposal #{proposal_id} [{['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NICE-TO-HAVE'][min(priority, 5)]}]
Title: {title}
Room: {proposal.get('room', '?')}
Description: {proposal.get('description', '')}
Rationale: {proposal.get('rationale', '')}

Write the complete SKILL.md content. Output only the file content — nothing else."""

    try:
        content = await call_local(prompt, system=system)
        model_used = "ollama"
    except Exception:
        content = await call_claude(prompt, system=system, room="armory")
        model_used = "claude"

    # Clean up: strip any preamble before the frontmatter
    if "---" in content:
        idx = content.index("---")
        content = content[idx:]

    return {
        "proposal_id": proposal_id,
        "proposal_title": title,
        "slug": slug,
        "version": version,
        "content": content,
        "model_used": model_used,
    }


async def save_skill(content: str, slug: str, version: int) -> dict:
    os.makedirs(SKILLS_DIR, exist_ok=True)
    os.makedirs(ARMORY_DIR, exist_ok=True)

    filename = f"{slug}_v{version}.md"
    fpath = os.path.join(SKILLS_DIR, filename)
    with open(fpath, "w") as f:
        f.write(content)

    # Mirror to vault for Obsidian visibility
    vault_skills_dir = os.path.join(BRAIN_PATH, "rooms", "armory", "skills")
    os.makedirs(vault_skills_dir, exist_ok=True)
    with open(os.path.join(vault_skills_dir, filename), "w") as f:
        f.write(content)

    # Update armory report log
    log_path = os.path.join(ARMORY_DIR, "latest_report.json")
    try:
        with open(log_path) as f:
            log = json.load(f)
    except Exception:
        log = {"skills_saved": []}

    log["skills_saved"].append({
        "filename": filename,
        "slug": slug,
        "version": version,
        "saved_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    })
    log["last_saved"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    log["total_skills"] = len(get_skills_list())

    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    return {
        "saved": True,
        "filename": filename,
        "path": fpath,
    }
