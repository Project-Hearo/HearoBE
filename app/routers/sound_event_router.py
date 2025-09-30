from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.database import get_db
from app.fcm import send_fcm_v1

from datetime import datetime, timezone
import logging


import re

router = APIRouter(prefix="/sound-events", tags=["Sound Events"])
logger = logging.getLogger("hearo.sound")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")



KO_LABEL_MAP = {
    "siren": "사이렌",
    "civil defense siren": "민방위 경보",
    "buzzer": "부저",
    "smoke detector": "화재 감지기 경보",
    "smoke alarm": "화재 감지기 경보",
    "fire alarm": "화재 경보",
    "explosion": "폭발",
    "boom": "폭음(쿵)",
    "baby cry": "아기 울음",
    "infant cry": "아기 울음",
    "screaming": "비명",
    "door": "문 여닫힘",
    "door-bell": "초인종",
    "door bell": "초인종",
    "doorbell": "초인종",
    "ding-dong": "딩동(초인종)",
    "knock": "노크",
    "water": "물 흐르는 소리",
    "dishes, pots, and pans": "설거지/그릇 부딪힘",
    "dishes": "설거지/그릇 부딪힘",
    "pots and pans": "설거지/그릇 부딪힘",
    "alarm": "경보음",
    "telephone": "전화기",
    "telephone bell ringing": "전화 벨소리",
    "ringtone": "벨소리",
    "telephone dialing": "전화 다이얼 소리",
    "dtmf": "전화 DTMF",
    "dial tone": "전화 연결음",
    "alarm clock": "알람시계",
    "splinter": "파편이 튀는 소리",
    "crack glass": "유리 금가는 소리",
    "glass crack": "유리 금가는 소리",
    "chink clink": "쨍그랑",
    "shatter": "산산조각 나는 소리",
    "boiling": "끓는 소리",
    "smash crash": "쾅/충돌",
    "breaking": "부서지는 소리",
    "crushing": "눌려 으스러지는 소리",
    "crumpling": "바스락",
    "crinkling": "바스락",
    "speech": "말소리",
}


def _normalize_labels(raw: str) -> list[str]:
    if not raw:
        return []
    s = raw.lower()
    s = re.sub(r"\([^)]*\)", "", s)

    parts = re.split(r"[\s,\/\|\+\;\t\r\n]+", s)
    cleaned = []
    for p in parts:
        p = p.strip().replace("_", " ").replace("-", " ")
        if p:
            cleaned.append(p)
    return cleaned


def _to_korean_labels(raw: str) -> list[str]:
    tokens = _normalize_labels(raw)
    seen = set()
    out = []
    for t in tokens:
        ko = KO_LABEL_MAP.get(t)
        if not ko:
            for en, ko2 in KO_LABEL_MAP.items():

                if all(word in t for word in en.split()):
                    ko = ko2
                    break
        if ko and ko not in seen:
            seen.add(ko)
            out.append(ko)
    return out


def make_push_body(sound_type: str, sound_detail: str | None) -> str:
    suffix = " 소리가 감지되었습니다."

    ko_labels = _to_korean_labels(sound_detail or "")
    if ko_labels:
        return f"{', '.join(ko_labels)}{suffix}"

    sound_type_map = {"danger": "위험", "help": "도움", "warning": "경고"}
    sound_type_ko = sound_type_map.get(sound_type, sound_type)
    return f"{sound_type_ko}{suffix}"


@router.post("/", response_model=schemas.SoundEventResponse)
def create_event(event: schemas.SoundEventCreate, db: Session = Depends(get_db)):

    payload = event.model_dump() if hasattr(event, "model_dump") else event.dict()
    db_event = models.SoundEvent(**payload)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    logger.info(f"[SoundEvent] received_at={now_utc_iso()} event_id={db_event.event_id}")


    body_text = make_push_body(event.sound_type, event.sound_detail)


    user = db.query(models.User).filter(models.User.user_id == event.user_id).first()
    user_name = getattr(user, "name", None) if user else None
    who = f"{user_name}님" if user_name else f"사용자(ID:{event.user_id})"

    # 사용자 푸시
    if user and getattr(user, "device_token", None):
        send_fcm_v1(
            token=user.device_token,
            title="새로운 소리 감지",
            body=body_text,
        )

        logger.info(f"[PushNotification] sent_at={now_utc_iso()} event_id={db_event.event_id} target=user user_id={event.user_id}")
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

        logger.info(f"[PushNotification] sent_at={now_utc_iso()} event_id={db_event.event_id} target=guardian guardian_id={gid} user_id={event.user_id}")
        seen.add(token)

    return db_event



@router.get("/", response_model=List[schemas.SoundEventResponse])
def read_events(db: Session = Depends(get_db)):
    return db.query(models.SoundEvent).all()


@router.get("/user/{user_id}", response_model=List[schemas.SoundEventResponse])
def read_user_events_by_date(
    user_id: int,
    date: str = Query(..., description="YYYY-MM-DD 형식"),
    db: Session = Depends(get_db),
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
