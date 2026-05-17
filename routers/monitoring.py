from fastapi import APIRouter
from agents.monitoring_room_mvp import run_monitoring, get_latest_report

router = APIRouter(prefix="/api/monitoring")


@router.post("/run")
async def run_monitoring_endpoint():
    return await run_monitoring()


@router.get("/status")
async def monitoring_status():
    report = await get_latest_report()
    return {"report": report}
