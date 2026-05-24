from fastapi import APIRouter
from pydantic import BaseModel
from agents.treasury_mvp import get_report, get_config, set_config, treasury_midnight_report

router = APIRouter(prefix="/api/treasury")


class CapRequest(BaseModel):
    daily_cap_usd: float


@router.get("/report")
async def treasury_report():
    return get_report()


@router.get("/config")
async def treasury_config():
    return get_config()


@router.post("/config")
async def treasury_set_config(req: CapRequest):
    return set_config(req.daily_cap_usd)


@router.post("/midnight-report")
async def treasury_midnight():
    return treasury_midnight_report()
