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

@router.post("/", response_model=schemas.SoundEventResponse)
def create_event(event: schemas.SoundEventCreate, db: Session = Depends(get_db)):

    payload = event.model_dump() if hasattr(event, "model_dump") else event.dict()
    db_event = models.SoundEvent(**payload)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    server_received_at = datetime.now(timezone.utc)
    occurred_at = getattr(db_event, "occurred_at", None)

    logger.info(
        "[SoundEvent/SAVED] event_id=%s user_id=%s type=%s detail=%s occurred_at=%s received_at=%s decibel=%s angle=%s loc=(%s,%s)",
        getattr(db_event, "event_id", None),
        db_event.user_id,
        db_event.sound_type,
        (db_event.sound_detail or "").strip(),
        occurred_at.isoformat() if isinstance(occurred_at, datetime) else occurred_at,
        server_received_at.isoformat(),
        getattr(db_event, "decibel", None),
        getattr(db_event, "angle", None),
        getattr(db_event, "location_x", None),
        getattr(db_event, "location_y", None),
    )

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
        try:
            send_fcm_v1(
                token=user.device_token,
                title="새로운 소리 감지",
                body=body_text,
            )
            logger.info("[FCM/USER] user_id=%s token=***%s title=%s body=%s",
                        event.user_id, str(user.device_token)[-6:], "새로운 소리 감지", body_text)
        except Exception as e:
            logger.error("[FCM/USER][ERROR] user_id=%s err=%s", event.user_id, e)
    else:
        logger.info("[FCM/USER][SKIP] user_id=%s reason=no_token", event.user_id)

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
            logger.info("[FCM/GUARDIAN][SKIP] guardian_id=%s user_id=%s reason=setting_blocked", gid, event.user_id)
            continue

        try:
            send_fcm_v1(
                token=token,
                title="보호자 알림",
                body=f"{who}: {body_text}",
            )
            logger.info("[FCM/GUARDIAN] guardian_id=%s user_id=%s token=***%s title=%s body=%s",
                        gid, event.user_id, str(token)[-6:], "보호자 알림", f"{who}: {body_text}")
            seen.add(token)
        except Exception as e:
            logger.error("[FCM/GUARDIAN][ERROR] guardian_id=%s user_id=%s err=%s", gid, event.user_id, e)


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
