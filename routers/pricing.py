from fastapi import APIRouter
from pydantic import BaseModel

from agents.pricing_room_mvp import apply_pricing, get_latest_report, run_pricing

router = APIRouter(prefix="/api/pricing")


class ApplyRequest(BaseModel):
    product_ids: list[int] | None = None
    dry_run: bool = True


@router.post("/run")
async def run_pricing_room():
    return await run_pricing()


@router.get("/status")
async def pricing_status():
    report = await get_latest_report()
    return {"report": report}


@router.post("/apply")
async def apply_prices(req: ApplyRequest):
    return await apply_pricing(product_ids=req.product_ids, dry_run=req.dry_run)
