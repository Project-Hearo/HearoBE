from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas, utils
from app.database import get_db
from datetime import datetime

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/", response_model=List[schemas.UserResponse])
def read_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()

@router.get("/{user_id}", response_model=schemas.UserResponse)
def read_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="해당 사용자가 없습니다.")
    return user

@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="해당 사용자가 없습니다.")
    db.delete(user)
    db.commit()
    return {"message": "사용자 삭제 완료"}

@router.post("/{user_id}/device-token")
def update_device_token(user_id: int, payload: schemas.DeviceTokenUpdate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="해당 사용자가 없습니다.")

    user.device_token = payload.token
    db.commit()
    return {"message": "token 저장 완료"}
