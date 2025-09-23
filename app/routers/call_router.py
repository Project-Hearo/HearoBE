from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app import models, schemas
from app.database import get_db
from app.fcm import send_fcm_v1

router = APIRouter(prefix="/call-events", tags=["Call Events"])

@router.post("", response_model=schemas.CallEventResponse)
def create_call_event(event: schemas.CallEventCreate, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(models.User.user_id == event.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db_event = models.CallEvent(user_id=event.user_id, created_at=datetime.utcnow())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    guardians = (
        db.query(models.Guardian)
        .join(models.UserGuardianLink, models.Guardian.guardian_id == models.UserGuardianLink.guardian_id)
        .filter(models.UserGuardianLink.user_id == event.user_id)
        .all()
    )

    for guardian in guardians:
        if guardian.device_token:
            send_fcm_v1(
                token=guardian.device_token,
                title="호출 알림",
                body=f"{user.name}님이 호출 버튼을 눌렀습니다!"
            )

    return db_event
