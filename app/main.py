import time

time.sleep(3)

from fastapi import FastAPI
from app.routers import auth_router, user_router,sound_event_router, push_notification_router, guardian_router, user_setting_router, guardian_user_setting_router
from app.database import engine, Base
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
