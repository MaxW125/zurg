import json
import os
from fastapi import APIRouter
from pydantic import BaseModel
from agents.researcher_room_mvp import run_researcher, start_loop, stop_loop, loop_status
from agents.designer_room_mvp import run_designer
from agents.factory_room_mvp import run_factory

BRAIN_PATH           = os.getenv("BRAIN_PATH", "./brain")
LAST_BRIEF_FILE      = os.path.join(BRAIN_PATH, "rooms", "captain", "last_brief.json")
PIPELINE_CONFIG_FILE = os.path.join(BRAIN_PATH, "rooms", "captain", "pipeline_config.json")


def _load_pipeline_config() -> dict:
    defaults = {"auto_design": False, "auto_approval": False}
    try:
        with open(PIPELINE_CONFIG_FILE) as f:
            return {**defaults, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults


def _save_pipeline_config(config: dict) -> None:
    os.makedirs(os.path.dirname(PIPELINE_CONFIG_FILE), exist_ok=True)
    with open(PIPELINE_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

router = APIRouter(prefix="/api/rooms")


class ResearchInput(BaseModel):
    direction: str = ""


class DesignInput(BaseModel):
    niche: str
    product_type: str
    target_audience: str
    keywords: list[str]
    design_direction: str


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
    """Return the most recently saved research brief (from any source)."""
    try:
        with open(LAST_BRIEF_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@router.get("/design/latest")
async def get_latest_design():
    """Return the most recently generated design (from any source)."""
    brain = os.getenv("BRAIN_PATH", "./brain")
    path = os.path.join(brain, "rooms", "captain", "last_design.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@router.get("/pipeline/config")
async def get_pipeline_config():
    """Return the current pipeline auto-mode settings."""
    return _load_pipeline_config()


class PipelineConfigUpdate(BaseModel):
    auto_design: bool | None = None
    auto_approval: bool | None = None


@router.post("/pipeline/config")
async def update_pipeline_config(body: PipelineConfigUpdate):
    """Update pipeline auto-mode settings."""
    config = _load_pipeline_config()
    if body.auto_design is not None:
        config["auto_design"] = body.auto_design
    if body.auto_approval is not None:
        config["auto_approval"] = body.auto_approval
    _save_pipeline_config(config)
    return config


@router.post("/design/run")
async def run_design_room(body: DesignInput):
    """Trigger the Designer agent directly."""
    return await run_designer(body.model_dump())


@router.post("/factory/run")
async def run_factory_room(body: FactoryInput):
    """Trigger the Factory agent directly — only called after owner approval."""
    return await run_factory(body.model_dump())
