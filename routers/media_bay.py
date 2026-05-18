from fastapi import APIRouter
from pydantic import BaseModel
from agents.media_bay_mvp import run_media_bay, get_latest_report

router = APIRouter(prefix="/api/media-bay")


class MediaBayInput(BaseModel):
    product_title:       str
    product_description: str = ""
    product_type:        str = "T-Shirt"
    mockup_url:          str = ""
    schedule_post:       bool = False


@router.post("/run")
async def run_media_bay_endpoint(body: MediaBayInput):
    return await run_media_bay(
        product_title=body.product_title,
        product_description=body.product_description,
        product_type=body.product_type,
        mockup_url=body.mockup_url,
        schedule_post=body.schedule_post,
    )


@router.get("/status")
async def media_bay_status():
    report = await get_latest_report()
    return {"report": report}
