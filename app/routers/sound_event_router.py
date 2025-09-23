from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.database import get_db
from app.fcm import send_fcm_v1

from fastapi import Query
from datetime import datetime, timezone
import logging

router = APIRouter(prefix="/sound-events", tags=["Sound Events"])
logger = logging.getLogger("hearo.sound")

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
@router.post("/", response_model=schemas.SoundEventResponse)
def create_event(event: schemas.SoundEventCreate, db: Session = Depends(get_db)):

    payload = event.model_dump() if hasattr(event, "model_dump") else event.dict()
    db_event = models.SoundEvent(**payload)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)


    logger.info(f"[SoundEvent] received_at={now_utc_iso()} event_id={db_event.event_id}")


    sound_type_map = {"danger": "위험", "help": "도움", "warning": "경고"}
    sound_type_ko = sound_type_map.get(event.sound_type, event.sound_type)

    raw = (event.sound_detail or "").strip()
    suffix = " 소리가 감지되었습니다."
    if raw:
        if raw.endswith("소리가 감지되었습니다."):
            body_text = raw
        elif raw.endswith("소리가 감지되었습니다"):
            body_text = raw + "."
        else:
            body_text = raw + suffix
    else:
        body_text = f"{sound_type_ko}{suffix}"

    user = db.query(models.User).filter(models.User.user_id == event.user_id).first()
    user_name = getattr(user, "name", None) if user else None
    who = f"{user_name}님" if user_name else f"사용자(ID:{event.user_id})"

    if user and getattr(user, "device_token", None):
        send_fcm_v1(
            token=user.device_token,
            title="새로운 소리 감지",
            body=body_text,
        )
    else:

        print("user의 FCM 토큰이 없습니다. (사용자 푸시는 스킵)")

    guardian_ids = []
    guardians = []
    try:
        if hasattr(models, "UserGuardianLink"):
            links = db.query(models.UserGuardianLink).filter(
                models.UserGuardianLink.user_id == event.user_id
            ).all()
            guardian_ids = [l.guardian_id for l in links]
        elif hasattr(models, "Guardian") and hasattr(models.Guardian, "user_id"):
            guardians = db.query(models.Guardian).filter(
                models.Guardian.user_id == event.user_id
            ).all()
    except Exception as e:
        print("보호자 링크 조회 중 예외:", e)

    if not guardians:
        if guardian_ids and hasattr(models, "Guardian"):
            guardians = db.query(models.Guardian).filter(
                models.Guardian.guardian_id.in_(guardian_ids)
            ).all()
        else:
            guardians = []

    allow_map = {}
    if hasattr(models, "GuardianUserSetting"):
        settings = db.query(models.GuardianUserSetting).filter(
            models.GuardianUserSetting.user_id == event.user_id
        ).all()
        allow_map = {s.guardian_id: getattr(s, event.sound_type, True) for s in settings}

    seen = set()
    for g in guardians:
        token = getattr(g, "device_token", None)
        gid = getattr(g, "guardian_id", None)
        if not token or token in seen:
            continue
        if allow_map and gid is not None and allow_map.get(gid, True) is False:
            continue
        send_fcm_v1(
            token=token,
            title="보호자 알림",
            body=f"{who}: {body_text}",
        )
        seen.add(token)


    logger.info(f"[PushNotification] sent_at={now_utc_iso()} event_id={db_event.event_id}")

    return db_event


@router.get("/", response_model=List[schemas.SoundEventResponse])
def read_events(db: Session = Depends(get_db)):
    return db.query(models.SoundEvent).all()


@router.get("/user/{user_id}", response_model=List[schemas.SoundEventResponse])
def read_user_events_by_date(
        user_id: int,
        date: str = Query(..., description="YYYY-MM-DD 형식"),
        db: Session = Depends(get_db)
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 잘못되었습니다. YYYY-MM-DD 형식이어야 합니다.")

    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    events = db.query(models.SoundEvent).filter(
        models.SoundEvent.user_id == user_id,
        models.SoundEvent.occurred_at >= start,
        models.SoundEvent.occurred_at <= end
    ).all()

    return events


@router.get("/", response_model=List[schemas.SoundEventResponse])
def read_events(db: Session = Depends(get_db)):
    return db.query(models.SoundEvent).all()


@router.get("/user/{user_id}", response_model=List[schemas.SoundEventResponse])
def read_user_events_by_date(
        user_id: int,
        date: str = Query(..., description="YYYY-MM-DD 형식"),
        db: Session = Depends(get_db)
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 잘못되었습니다. YYYY-MM-DD 형식이어야 합니다.")

    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    events = db.query(models.SoundEvent).filter(
        models.SoundEvent.user_id == user_id,
        models.SoundEvent.occurred_at >= start,
        models.SoundEvent.occurred_at <= end
    ).all()

    return events


@router.get("/user/{user_id}/events", response_model=List[schemas.SoundEventResponse])
def read_user_all_events(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.SoundEvent).filter(
        models.SoundEvent.user_id == user_id
    ).all()
