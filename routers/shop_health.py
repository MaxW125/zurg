from fastapi import APIRouter
from agents.shop_health_room_mvp import run_shop_health, get_latest_report

router = APIRouter(prefix="/api/shop-health")


@router.post("/run")
async def run_shop_health_room():
    return await run_shop_health()


@router.get("/status")
async def shop_health_status():
    report = await get_latest_report()
    return {"report": report}
