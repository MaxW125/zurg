import json
import os
from fastapi import APIRouter
from pydantic import BaseModel
from agents.researcher_room_mvp import run_researcher, start_loop, stop_loop, loop_status, researcher_midnight_report
from agents.designer_room_mvp import run_designer, designer_midnight_report
from agents.factory_room_mvp import run_factory, factory_midnight_report
from agents.approval_room_mvp import approval_midnight_report
from agents.notify import notify

router = APIRouter(prefix="/api/rooms")


class ResearchInput(BaseModel):
    direction: str = ""


class DesignInput(BaseModel):
    niche: str
    product_type: str
    target_audience: str
    keywords: list[str]
    design_direction: str
    denial_context: str = ""


class FactoryInput(BaseModel):
    niche: str
    product_type: str
    image_path: str
    image_prompt: str = ""
    keywords: list[str] = []


@router.post("/research/run")
async def run_research_room(body: ResearchInput):
    """Trigger the Researcher agent directly."""
    return await run_researcher({"direction": body.direction})


@router.post("/research/autonomous/start")
async def start_autonomous():
    """Start the autonomous research loop."""
    started = start_loop()
    return {"started": started, "status": loop_status()}


@router.post("/research/autonomous/stop")
async def stop_autonomous():
    """Stop the autonomous research loop."""
    stopped = stop_loop()
    return {"stopped": stopped, "status": loop_status()}


@router.get("/research/autonomous/status")
async def get_autonomous_status():
    """Return current autonomous loop status."""
    return loop_status()


@router.get("/research/latest-brief")
async def get_latest_brief():
    """Return the most recently saved research brief."""
    brain = os.getenv("BRAIN_PATH", "./brain")
    path = os.path.join(brain, "rooms", "captain", "last_brief.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@router.get("/design/latest")
async def get_latest_design():
    """Return the most recently saved design."""
    brain = os.getenv("BRAIN_PATH", "./brain")
    path = os.path.join(brain, "rooms", "captain", "last_design.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@router.post("/design/run")
async def run_design_room(body: DesignInput):
    """Trigger the Designer agent directly."""
    try:
        result = await run_designer(body.model_dump())
    except Exception as e:
        await notify(
            f"❌ Designer failed for: {body.niche} — {body.product_type}\n"
            f"Error: {str(e)[:200]}\n"
            "Check logs: ~/zurg/logs/server.log"
        )
        raise

    brain = os.getenv("BRAIN_PATH", "./brain")
    path = os.path.join(brain, "rooms", "captain", "last_design.json")
    try:
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
    except Exception:
        pass

    # Route to auto-approve if we have enough verdict history (Phase 2+)
    from agents.approval_room_mvp import auto_decide, _load_verdict_history
    all_verdicts = _load_verdict_history()
    verdict_count = sum(1 for v in all_verdicts if v.get("source", "manual") == "manual")

    if verdict_count >= 100:
        # Autonomous mode — agent decides, no text to owner
        decision = await auto_decide(result)
        if decision["approved"]:
            from agents.factory_room_mvp import run_factory
            try:
                product = await run_factory(result)
                await notify(
                    f"✅ Auto-approved & published: {product['title']}\n"
                    f"Shopify: {product['product_url']}"
                )
            except Exception as e:
                await notify(f"⚠️ Auto-approved but factory failed for {result['niche']}: {str(e)[:120]}")
        else:
            await notify(
                f"❌ Auto-rejected: {result['niche']} — {result['product_type']}\n"
                f"Reason: {decision['reasoning'][:120]}"
            )
    else:
        # Manual mode — text owner to open Approval Room
        redesign_note = " (redesign)" if body.denial_context else ""
        await notify(
            f"🎨 Design ready{redesign_note}: {result['niche']} — {result['product_type']}\n"
            "Open the Approval Room to approve or deny."
        )

    return result


@router.post("/factory/run")
async def run_factory_room(body: FactoryInput):
    """Trigger the Factory agent directly — only called after owner approval."""
    return await run_factory(body.model_dump())


@router.post("/research/midnight-report")
async def research_midnight():
    return researcher_midnight_report()


@router.post("/design/midnight-report")
async def design_midnight():
    return designer_midnight_report()


@router.post("/approval/midnight-report")
async def approval_midnight():
    return approval_midnight_report()


@router.post("/factory/midnight-report")
async def factory_midnight():
    return factory_midnight_report()
