from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agents.factory_room_mvp import run_factory

router = APIRouter(prefix="/api/approval")


class ApprovalDecision(BaseModel):
    approved: bool
    niche: str = ""
    product_type: str = ""
    image_path: str = ""
    image_prompt: str = ""
    keywords: list[str] = []
    design_direction: str = ""


@router.post("/decide")
async def decide_approval(body: ApprovalDecision):
    """
    Owner approves or rejects a design.
    - approved=True  → Factory agent publishes to Shopify
    - approved=False → returns rejection acknowledgement
    """
    if not body.approved:
        return {
            "approved": False,
            "message": "Design rejected. Run the Designer again to generate a new one.",
        }

    if not body.image_path:
        raise HTTPException(status_code=400, detail="image_path is required to publish")

    product = await run_factory(body.model_dump())

    return {
        "approved": True,
        "message": f"Published to Shopify: {product['title']}",
        "product": product,
    }
