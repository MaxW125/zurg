import os
import json
import glob
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from agents.factory_room_mvp import run_factory
from agents.designer_room_mvp import run_designer
from agents.approval_room_mvp import analyze_design, auto_decide
from agents.notify import notify

router = APIRouter(prefix="/api/approval")

BRAIN_PATH = os.getenv("BRAIN_PATH", "./brain")


class DesignAnalysisRequest(BaseModel):
    niche: str = ""
    product_type: str = ""
    image_path: str = ""
    image_prompt: str = ""


class ApprovalDecision(BaseModel):
    approved: bool
    feedback: str = ""
    niche: str = ""
    product_type: str = ""
    image_path: str = ""
    image_prompt: str = ""
    keywords: list[str] = []
    design_direction: str = ""


def _save_verdict(decision: ApprovalDecision) -> None:
    """Write a verdict markdown file to brain/approvals/ for the Approval Agent to learn from."""
    approvals_dir = os.path.join(BRAIN_PATH, "rooms", "approval", "verdicts")
    os.makedirs(approvals_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    verdict_word = "approved" if decision.approved else "rejected"
    slug = decision.niche.lower().replace(" ", "_")[:30] if decision.niche else "unknown"
    filename = f"verdict_{timestamp}_{verdict_word}_{slug}.md"
    filepath = os.path.join(approvals_dir, filename)

    content = f"""# Verdict: {verdict_word}
Date: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC
Niche: {decision.niche}
Product: {decision.product_type}
Image: {decision.image_path}

## Owner Feedback
{decision.feedback or "(no feedback provided)"}

## Tags
niche:{decision.niche.lower().replace(" ", "-")} product:{decision.product_type.lower().replace(" ", "-")} verdict:{verdict_word}
"""
    with open(filepath, "w") as f:
        f.write(content)


def _load_verdicts() -> list[dict]:
    """Return all verdicts as a list, sorted oldest-first."""
    approvals_dir = os.path.join(BRAIN_PATH, "rooms", "approval", "verdicts")
    if not os.path.isdir(approvals_dir):
        return []

    verdicts = []
    for path in sorted(glob.glob(os.path.join(approvals_dir, "verdict_*.md"))):
        try:
            with open(path) as f:
                content = f.read()
            lines = content.splitlines()
            verdict = {
                "approved": "# Verdict: approved" in lines[0] if lines else False,
                "niche": "",
                "date": "",
                "feedback": "",
            }
            for line in lines:
                if line.startswith("Date:"):
                    verdict["date"] = line.replace("Date:", "").strip()
                elif line.startswith("Niche:"):
                    verdict["niche"] = line.replace("Niche:", "").strip()
            # Extract feedback (section after "## Owner Feedback")
            if "## Owner Feedback" in content:
                feedback_section = content.split("## Owner Feedback", 1)[1]
                verdict["feedback"] = feedback_section.split("##")[0].strip()
            verdicts.append(verdict)
        except Exception:
            continue

    return verdicts


@router.post("/auto-decide")
async def auto_decide_approval(body: ApprovalDecision):
    """
    Autonomous mode: agent makes the approve/reject call, saves the verdict,
    and publishes to Shopify if approved — no owner input required.
    """
    result = await auto_decide(body.model_dump())

    # Build a full decision with agent reasoning as feedback
    decision = ApprovalDecision(
        approved=result["approved"],
        feedback=f"[AUTO] {result['reasoning']}",
        niche=body.niche,
        product_type=body.product_type,
        image_path=body.image_path,
        image_prompt=body.image_prompt,
        keywords=body.keywords,
        design_direction=body.design_direction,
    )
    _save_verdict(decision)

    if not result["approved"]:
        await notify(f"❌ Auto-rejected: {body.niche} {body.product_type}\nReason: {result['reasoning'][:120]}")
        return {
            "approved": False,
            "reasoning": result["reasoning"],
            "message": "Agent rejected this design.",
        }

    if not body.image_path:
        raise HTTPException(status_code=400, detail="image_path is required to publish")

    product = await run_factory(body.model_dump())

    return {
        "approved": True,
        "reasoning": result["reasoning"],
        "message": f"Agent approved and published: {product['title']}",
        "product": product,
    }


@router.post("/analyze")
async def get_analysis(body: DesignAnalysisRequest):
    """Approval Agent analyzes a design against verdict history. Called when opening the Approval Room."""
    return await analyze_design(body.model_dump())


@router.get("/verdicts")
async def get_verdicts():
    """Return all stored verdicts — used by the Approval Room panel to show history."""
    return _load_verdicts()


async def _trigger_redesign(feedback: str, body: ApprovalDecision) -> None:
    """Load the last brief, inject denial feedback, and re-run the designer."""
    brain = os.getenv("BRAIN_PATH", "./brain")
    brief_path = os.path.join(brain, "rooms", "captain", "last_brief.json")
    try:
        with open(brief_path) as f:
            brief = json.load(f)
    except Exception:
        brief = {
            "niche": body.niche,
            "product_type": body.product_type,
            "target_audience": "",
            "keywords": body.keywords,
            "design_direction": body.design_direction,
        }

    brief["denial_context"] = feedback or "No specific feedback — try a different visual approach."

    try:
        design = await run_designer(brief)
        design_path = os.path.join(brain, "rooms", "captain", "last_design.json")
        with open(design_path, "w") as f:
            json.dump(design, f, indent=2)
        await notify(
            f"🎨 Redesign ready: {design['niche']} — {design['product_type']}\n"
            "Open the Approval Room to approve or deny."
        )
    except Exception as e:
        await notify(f"⚠️ Redesign failed for {body.niche}: {str(e)[:100]}")


@router.post("/decide")
async def decide_approval(body: ApprovalDecision, background_tasks: BackgroundTasks):
    """
    Owner approves or rejects a design.
    - Always saves a verdict file for the Approval Agent to learn from.
    - approved=True  → Factory publishes to Shopify + Etsy, notifies owner
    - approved=False → saves rejection, triggers redesign in background with feedback
    """
    _save_verdict(body)

    if not body.approved:
        background_tasks.add_task(_trigger_redesign, body.feedback, body)
        return {
            "approved": False,
            "message": "Design rejected. Zurg is generating a new design — you'll get a text when it's ready.",
        }

    if not body.image_path:
        raise HTTPException(status_code=400, detail="image_path is required to publish")

    product = await run_factory(body.model_dump())

    return {
        "approved": True,
        "message": f"Published to Shopify: {product['title']}",
        "product": product,
    }
