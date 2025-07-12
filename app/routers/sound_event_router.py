from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.database import get_db

from fastapi import Query
from datetime import datetime
router = APIRouter(prefix="/sound-events", tags=["Sound Events"])

@router.post("/", response_model=schemas.SoundEventResponse)
def create_event(event: schemas.SoundEventCreate, db: Session = Depends(get_db)):
    db_event = models.SoundEvent(**event.dict())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
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