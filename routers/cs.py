from fastapi import APIRouter
from agents.cs_room_mvp import run_cs, get_latest_report

router = APIRouter(prefix="/api/cs")


@router.post("/run")
async def run_cs_room():
    return await run_cs()


@router.get("/status")
async def cs_status():
    report = await get_latest_report()
    return {"report": report}
