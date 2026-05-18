from fastapi import APIRouter
from pydantic import BaseModel
from agents.armory_mvp import generate_skill, save_skill, get_skills_list

router = APIRouter(prefix="/api/armory")


class GenerateRequest(BaseModel):
    proposal_id: int


class SaveRequest(BaseModel):
    content: str
    slug: str
    version: int


@router.post("/generate")
async def armory_generate(req: GenerateRequest):
    return await generate_skill(req.proposal_id)


@router.post("/save")
async def armory_save(req: SaveRequest):
    return await save_skill(req.content, req.slug, req.version)


@router.get("/skills")
async def armory_skills():
    return {"skills": get_skills_list()}
