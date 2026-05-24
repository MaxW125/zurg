from fastapi import APIRouter
from pydantic import BaseModel
from agents.pricing_room_mvp import run_pricing, get_latest_report, apply_price_change, apply_etsy_price_change

router = APIRouter(prefix="/api/pricing")


class ApplyPriceRequest(BaseModel):
    variant_id: int
    new_price: str


class ApplyEtsyPriceRequest(BaseModel):
    listing_id: int
    new_price: float


@router.post("/run")
async def run_pricing_room():
    return await run_pricing()


@router.get("/status")
async def pricing_status():
    report = await get_latest_report()
    return {"report": report}


@router.post("/apply")
async def apply_price(req: ApplyPriceRequest):
    variant = await apply_price_change(req.variant_id, req.new_price)
    return {"ok": True, "variant_id": variant.get("id"), "price": variant.get("price")}


@router.post("/apply-etsy")
async def apply_etsy_price(req: ApplyEtsyPriceRequest):
    result = await apply_etsy_price_change(req.listing_id, req.new_price)
    return {"ok": True, "listing_id": req.listing_id, "new_price": req.new_price}
