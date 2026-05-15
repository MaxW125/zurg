import os
import glob
from agents.llm_client import call_local, call_claude
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
You must make a binary approve/reject decision on each design based on the owner's taste history.

Rules:
- Study the verdict history carefully — approve designs similar to past approvals, reject those similar to past rejections
- With no history, approve by default (owner can always reject manually later)
- Be decisive — no hedging
- Output MUST start with exactly one of these lines:
  DECISION: APPROVE
  DECISION: REJECT
- Follow immediately with REASONING: and 1-2 sentences explaining your decision"""


def _load_verdict_history() -> list[dict]:
    """Load all verdict files from brain/approvals/."""
    approvals_dir = os.path.join(BRAIN_PATH, "approvals")
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
                "feedback": "",
            }
            for line in lines:
                if line.startswith("Niche:"):
                    verdict["niche"] = line.replace("Niche:", "").strip()
            if "## Owner Feedback" in content:
                feedback_section = content.split("## Owner Feedback", 1)[1]
                verdict["feedback"] = feedback_section.split("##")[0].strip()
            verdicts.append(verdict)
        except Exception:
            continue

    return verdicts


def _build_analysis_prompt(design: dict, verdicts: list[dict]) -> str:
    verdict_count = len(verdicts)
    approved_count = sum(1 for v in verdicts if v["approved"])
    rejected_count = verdict_count - approved_count

    if verdict_count == 0:
        history_context = "No verdict history yet — this is the first design you've reviewed."
    else:
        recent = verdicts[-5:]
        history_lines = []
        for v in recent:
            status = "APPROVED" if v["approved"] else "REJECTED"
            feedback = v["feedback"][:100] if v["feedback"] else "(no feedback)"
            history_lines.append(f"  [{status}] {v['niche']} — \"{feedback}\"")
        history_context = (
            f"Verdict history: {approved_count} approved, {rejected_count} rejected "
            f"out of {verdict_count} total.\n\nRecent verdicts:\n" + "\n".join(history_lines)
        )

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

    Returns:
      - analysis: the agent's text assessment
      - verdict_count: how many verdicts have been collected
      - phase: 1, 2, or 3
      - model_used: which LLM generated the analysis
    """
    verdicts = _load_verdict_history()
    verdict_count = len(verdicts)
    phase = 1 if verdict_count < 100 else (2 if verdict_count < 200 else 3)

    prompt = _build_analysis_prompt(design, verdicts)
    analysis_system = load_system_prompt("approval", "approval", _ANALYSIS_FALLBACK)
    model_used = "ollama"
    try:
        analysis = await call_local(prompt, system=analysis_system)
    except Exception:
        model_used = "claude"
        analysis = await call_claude(prompt, system=analysis_system)

    return {
        "analysis": analysis,
        "verdict_count": verdict_count,
        "phase": phase,
        "model_used": model_used,
    }


async def auto_decide(design: dict) -> dict:
    """
    Autonomous mode: agent makes the approve/reject call without owner input.
    Parses a structured DECISION: APPROVE/REJECT response from the LLM.

    Returns:
      - approved: bool
      - reasoning: the agent's explanation
      - verdict_count: how many past verdicts informed the decision
      - model_used
    """
    verdicts = _load_verdict_history()
    verdict_count = len(verdicts)

    prompt = _build_analysis_prompt(design, verdicts).replace(
        "Give a 2-3 sentence assessment. Be specific. Reference past verdicts if relevant.",
        "Make an approve/reject decision. Start with DECISION: APPROVE or DECISION: REJECT, "
        "then REASONING: followed by 1-2 sentences.",
    )

    auto_decide_system = load_system_prompt("approval", "approval", _AUTO_DECIDE_FALLBACK)
    model_used = "ollama"
    try:
        raw = await call_local(prompt, system=auto_decide_system)
    except Exception:
        model_used = "claude"
        raw = await call_claude(prompt, system=auto_decide_system)

    # Parse structured output
    approved = True  # default to approve if parsing fails
    reasoning = raw.strip()

    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("DECISION:"):
            decision_word = line.split(":", 1)[1].strip().upper()
            approved = decision_word == "APPROVE"
        if line.upper().startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()

    return {
        "approved": approved,
        "reasoning": reasoning,
        "verdict_count": verdict_count,
        "model_used": model_used,
    }
