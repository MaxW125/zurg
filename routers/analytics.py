from fastapi import APIRouter
from agents.analytics_room_mvp import run_analytics, get_latest_report

router = APIRouter(prefix="/api/analytics")


@router.post("/run")
async def run_analytics_room():
    return await run_analytics()


@router.get("/status")
async def analytics_status():
    report = await get_latest_report()
    return {"report": report}
