from fastapi import APIRouter
from pydantic import BaseModel
from agents.memory_room_mvp import get_vault_stats, compress_vault, export_cold_storage, run_index, memory_midnight_report

router = APIRouter(prefix="/api/memory")


class CompressRequest(BaseModel):
    keep_n: int = 5


@router.get("/stats")
async def memory_stats():
    return get_vault_stats()


@router.post("/compress")
async def memory_compress(req: CompressRequest):
    return compress_vault(keep_n=req.keep_n)


@router.post("/export")
async def memory_export():
    return export_cold_storage()


@router.post("/index")
async def memory_index():
    return run_index()


@router.post("/midnight-report")
async def memory_midnight():
    return memory_midnight_report()
