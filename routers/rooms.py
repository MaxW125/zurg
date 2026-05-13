from fastapi import APIRouter
from pydantic import BaseModel
from agents.researcher_room_mvp import run_researcher
from agents.designer_room_mvp import run_designer
from agents.factory_room_mvp import run_factory

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


@router.post("/design/run")
async def run_design_room(body: DesignInput):
    """Trigger the Designer agent directly."""
    return await run_designer(body.model_dump())


@router.post("/factory/run")
async def run_factory_room(body: FactoryInput):
    """Trigger the Factory agent directly — only called after owner approval."""
    return await run_factory(body.model_dump())
