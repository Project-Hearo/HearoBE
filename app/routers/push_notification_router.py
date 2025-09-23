from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/notifications", tags=["Push Notifications"])

@router.post("/", response_model=schemas.PushNotificationResponse)
def create_notification(notification: schemas.PushNotificationCreate, db: Session = Depends(get_db)):
    db_notification = models.PushNotification(**notification.dict())
    db.add(db_notification)
    db.commit()
    db.refresh(db_notification)
    return db_notification

@router.get("/", response_model=List[schemas.PushNotificationResponse])
def read_notifications(db: Session = Depends(get_db)):
    return db.query(models.PushNotification).all()

@router.get("/user/{user_id}", response_model=List[schemas.PushNotificationResponse])
def read_user_notifications(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.PushNotification).filter(models.PushNotification.user_id == user_id).all()
