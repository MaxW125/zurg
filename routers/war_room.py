from fastapi import APIRouter
from agents.war_room_mvp import run_war_room, get_latest_report

router = APIRouter(prefix="/api/war-room")


@router.post("/run")
async def run_war_room_endpoint():
    return await run_war_room()


@router.get("/status")
async def war_room_status():
    report = await get_latest_report()
    return {"report": report}
