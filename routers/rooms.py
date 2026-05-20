import json
import os
from fastapi import APIRouter
from pydantic import BaseModel
from agents.researcher_room_mvp import run_researcher, start_loop, stop_loop, loop_status
from agents.designer_room_mvp import run_designer
from agents.factory_room_mvp import run_factory
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
    result = await run_designer(body.model_dump())
    brain = os.getenv("BRAIN_PATH", "./brain")
    path = os.path.join(brain, "rooms", "captain", "last_design.json")
    try:
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
    except Exception:
        pass
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
