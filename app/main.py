import time

time.sleep(3)

from fastapi import FastAPI
from app.routers import auth_router, user_router,sound_event_router, push_notification_router, guardian_router, user_setting_router, guardian_user_setting_router,  map_router
from app.database import engine, Base
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from app.map_generator import generate_wall_and_meta
import os

from app.mqtt_bus import mqtt_bus
from app.routers import slam
from fastapi.responses import FileResponse
from pathlib import Path
from fastapi import HTTPException


load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(guardian_router.router)
app.include_router(sound_event_router.router)
app.include_router(push_notification_router.router)
app.include_router(user_setting_router.router)
app.include_router(guardian_user_setting_router.router)
app.include_router(map_router.router)
app.include_router(slam.router)


APP_DIR = Path(__file__).resolve().parent
PROJ_DIR = APP_DIR.parent
PUBLIC_DIR = PROJ_DIR / "public"
FRONTEND_DIR = PROJ_DIR / "frontend" / "build"

@app.get("/map-config.json")
def get_map_config():
    p = PUBLIC_DIR / "map-config.json"
    if not p.exists():
        raise HTTPException(404, detail=f"{p} not found")
    return FileResponse(p)

@app.get("/wall_shell.json")
def get_wall_shell():
    p = PUBLIC_DIR / "wall_shell.json"
    if not p.exists():
        raise HTTPException(404, detail=f"{p} not found")
    return FileResponse(p)

@app.get("/meta.json")
def get_meta():
    p = PUBLIC_DIR / "meta.json"
    if not p.exists():
        raise HTTPException(404, detail=f"{p} not found")
    return FileResponse(p)

# /maps/* (yaml/pgm/png 등) 정적 서빙
# public/maps 가 없으면 자동 생성
(PUBLIC_DIR / "maps").mkdir(parents=True, exist_ok=True)
app.mount("/maps", StaticFiles(directory=str(PUBLIC_DIR / "maps"), html=False), name="maps")

@app.on_event("startup")
def _startup():
    # MQTT 브로커 연결
    mqtt_bus.start()
    # 맵 관련 JSON 생성
    try:
        generate_wall_and_meta()
    except Exception as e:
        print("[Map Init Error]", e)


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
