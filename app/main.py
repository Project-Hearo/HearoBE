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

@app.on_event("startup")
def _startup():
    # MQTT 브로커 연결 시작
    mqtt_bus.start()

def startup_event():
    try:
        generate_wall_and_meta()
    except Exception as e:
        print("[Map Init Error]", e)


app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")