from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Zurg MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import chat, rooms, approval, analytics, pricing, cs, shop_health, war_room, monitoring, media_bay, radar_bay, armory
app.include_router(chat.router)
app.include_router(rooms.router)
app.include_router(approval.router)
app.include_router(analytics.router)
app.include_router(pricing.router)
app.include_router(cs.router)
app.include_router(shop_health.router)
app.include_router(war_room.router)
app.include_router(monitoring.router)
app.include_router(media_bay.router)
app.include_router(radar_bay.router)
app.include_router(armory.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="frontend/public", html=True), name="static")
