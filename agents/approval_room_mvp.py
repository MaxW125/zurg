import os
import glob
import json
from datetime import datetime, timezone, timedelta
from agents.llm_client import call_claude
from agents.brain import load_system_prompt

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")

_ANALYSIS_FALLBACK = """You are the Approval Agent for a print-on-demand business.
Your job is to evaluate a design against the owner's taste history and give a brief, honest assessment.

Rules:
- Be direct and specific — no fluff
- Reference past verdicts when relevant (e.g. "similar to the cat design you approved")
- Flag genuine weaknesses (generic concept, wrong style for niche, etc.)
- If you have no verdict history yet, say so and note that you're learning
- Output 2-3 sentences maximum"""

_AUTO_DECIDE_FALLBACK = """You are the Approval Agent for a print-on-demand business operating in autonomous mode.
You must make a binary approve/reject decision on each design based solely on the owner's verdict history.

Rules:
- Study the verdict history carefully — your job is to replicate the owner's taste, not your own
- Approve designs similar in niche, style, and product type to past approvals
- Reject designs similar to past rejections, or that repeat the same feedback patterns
- If verdict history is thin (under 20), lean toward approving — the owner can correct you
- Be decisive — no hedging
- Output MUST start with exactly one of these lines:
  DECISION: APPROVE
  DECISION: REJECT
- Follow immediately with REASONING: and 1-2 sentences grounded in the verdict history"""


def _load_verdict_history() -> list[dict]:
    """Load all verdict files from the approval vault."""
    approvals_dir = os.path.join(BRAIN_PATH, "rooms", "approval", "verdicts")
    if not os.path.isdir(approvals_dir):
        return []

    verdicts = []
    for path in sorted(glob.glob(os.path.join(approvals_dir, "verdict_*.md"))):
        try:
            with open(path) as f:
                content = f.read()
            lines = content.splitlines()
            verdict: dict = {
                "approved": "# Verdict: approved" in (lines[0] if lines else ""),
                "niche": "",
                "product_type": "",
                "title": "",
                "feedback": "",
            }
            for line in lines:
                if line.startswith("Niche:"):
                    verdict["niche"] = line.replace("Niche:", "").strip()
                elif line.startswith("Product:"):
                    verdict["product_type"] = line.replace("Product:", "").strip()
                elif line.startswith("Title:"):
                    verdict["title"] = line.replace("Title:", "").strip()
                elif line.startswith("Source:"):
                    verdict["source"] = line.replace("Source:", "").strip()
            # Parse field verdicts (per-field pass/fail lines)
            field_feedback = ""
            if "## Field Verdicts" in content:
                field_section = content.split("## Field Verdicts", 1)[1]
                field_section = field_section.split("##")[0].strip()
                # Keep only the lines that flagged bad fields
                bad_lines = [l for l in field_section.splitlines() if "✗ BAD" in l]
                if bad_lines:
                    field_feedback = "; ".join(bad_lines)
            # Owner summary (assembled from per-field parts)
            summary_feedback = ""
            if "## Owner Feedback" in content:
                feedback_section = content.split("## Owner Feedback", 1)[1]
                summary_feedback = feedback_section.split("##")[0].strip()
                if summary_feedback == "(no summary provided)":
                    summary_feedback = ""
            # Combine: prefer summary, append field detail if present
            verdict["feedback"] = " | ".join(filter(None, [summary_feedback, field_feedback])) or "(no feedback)"
            verdicts.append(verdict)
        except Exception:
            continue

    return verdicts


def _build_history_context(verdicts: list[dict], recent_count: int = 5) -> str:
    verdict_count = len(verdicts)
    approved_count = sum(1 for v in verdicts if v["approved"])
    rejected_count = verdict_count - approved_count

    if verdict_count == 0:
        return "No verdict history yet — this is the first design reviewed."

    recent = verdicts[-recent_count:]
    history_lines = []
    for v in recent:
        status = "APPROVED" if v["approved"] else "REJECTED"
        feedback = v["feedback"][:120] if v["feedback"] else "(no feedback)"
        product = v.get("product_type", "")
        history_lines.append(f"  [{status}] {v['niche']} — {product} — \"{feedback}\"")

    return (
        f"Verdict history: {approved_count} approved, {rejected_count} rejected "
        f"out of {verdict_count} total.\n\nRecent verdicts:\n" + "\n".join(history_lines)
    )


def _build_analysis_prompt(design: dict, verdicts: list[dict], recent_count: int = 5) -> str:
    history_context = _build_history_context(verdicts, recent_count)
    return f"""Evaluate this design for the owner's approval decision.

Design details:
  Niche: {design.get('niche', 'unknown')}
  Product type: {design.get('product_type', 'unknown')}
  Image prompt used: {design.get('image_prompt', 'not provided')}

{history_context}

Give a 2-3 sentence assessment. Be specific. Reference past verdicts if relevant."""


async def analyze_design(design: dict) -> dict:
    """
    Phase 1 analysis: load verdict history, generate a brief assessment of the design.
    Shown to the owner in the Approval Room panel before they decide.
    """
    verdicts = _load_verdict_history()
    verdict_count = len(verdicts)
    phase = 1 if verdict_count < 100 else (2 if verdict_count < 200 else 3)

    prompt = _build_analysis_prompt(design, verdicts, recent_count=5)
    analysis_system = load_system_prompt("approval", "approval", _ANALYSIS_FALLBACK)
    analysis = await call_claude(prompt, system=analysis_system, room="approval")

    return {
        "analysis": analysis,
        "verdict_count": verdict_count,
        "phase": phase,
        "model_used": "claude",
    }


async def auto_decide(design: dict) -> dict:
    """
    Autonomous mode: agent makes the approve/reject call without owner input.
    Uses the last 25 verdicts so the decision is grounded in recent taste signals.
    """
    all_verdicts = _load_verdict_history()
    # Only train on manual verdicts — auto verdicts can compound errors over time
    verdicts = [v for v in all_verdicts if v.get("source", "manual") == "manual"]
    verdict_count = len(verdicts)

    prompt = _build_analysis_prompt(design, verdicts, recent_count=len(verdicts)).replace(
        "Give a 2-3 sentence assessment. Be specific. Reference past verdicts if relevant.",
        "Make an approve/reject decision. Start with DECISION: APPROVE or DECISION: REJECT, "
        "then REASONING: followed by 1-2 sentences grounded in the verdict history.",
    )

    auto_decide_system = load_system_prompt("approval", "approval", _AUTO_DECIDE_FALLBACK)
    raw = await call_claude(prompt, system=auto_decide_system, room="approval")

    approved = True  # default approve if parsing fails
    reasoning = raw.strip()

    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("DECISION:"):
            approved = line.split(":", 1)[1].strip().upper() == "APPROVE"
        if line.upper().startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()

    return {
        "approved": approved,
        "reasoning": reasoning,
        "verdict_count": verdict_count,
        "model_used": "claude",
    }


def approval_midnight_report() -> dict:
    cst = timezone(timedelta(hours=-6))
    today_start = datetime.now(cst).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_str = datetime.now(cst).strftime("%Y-%m-%d")

    verdicts_dir = os.path.join(BRAIN_PATH, "rooms", "approval", "verdicts")
    report_dir = os.path.join(BRAIN_PATH, "rooms", "approval", "reports")

    approved_today = 0
    rejected_today = 0
    verdicts_today = []

    if os.path.isdir(verdicts_dir):
        for fname in sorted(os.listdir(verdicts_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(verdicts_dir, fname)
            if os.path.getmtime(fpath) < today_start:
                continue
            verdict_type = "approved" if "_approved_" in fname else "rejected"
            niche, product_type = "", ""
            try:
                lines = open(fpath).read().splitlines()
                for line in lines:
                    if line.startswith("Niche:"):
                        niche = line.replace("Niche:", "").strip()
                    elif line.startswith("Product:"):
                        product_type = line.replace("Product:", "").strip()
            except Exception:
                pass
            if verdict_type == "approved":
                approved_today += 1
            else:
                rejected_today += 1
            verdicts_today.append({"verdict": verdict_type, "niche": niche, "product_type": product_type})

    nothing = not verdicts_today
    data = {
        "run_date":          today_str,
        "nothing_to_report": nothing,
        "approved_today":    approved_today,
        "rejected_today":    rejected_today,
        "total_today":       approved_today + rejected_today,
        "verdicts":          verdicts_today,
    }

    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, "latest_report.json"), "w") as f:
        json.dump(data, f, indent=2)

    return data
