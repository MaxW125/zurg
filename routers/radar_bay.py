from fastapi import APIRouter
from agents.radar_bay_mvp import run_radar_bay, get_latest_report

router = APIRouter(prefix="/api/radar-bay")


@router.post("/run")
async def run_radar_bay_endpoint():
    return await run_radar_bay()


@router.get("/status")
async def radar_bay_status():
    report = await get_latest_report()
    return {"report": report}
