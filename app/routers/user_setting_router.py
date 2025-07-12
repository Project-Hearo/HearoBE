from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/user-settings", tags=["User Settings"])

@router.get("/", response_model=List[schemas.UserSetting])
def get_all_settings(db: Session = Depends(get_db)):
    return db.query(models.UserSetting).all()
@router.get("/{user_id}", response_model=schemas.UserSetting)
def get_user_setting(user_id: int, db: Session = Depends(get_db)):
    db_setting = db.query(models.UserSetting).filter(models.UserSetting.user_id == user_id).first()
    if not db_setting:
        raise HTTPException(status_code=404, detail="설정 없음")
    return db_setting

@router.put("/{user_id}", response_model=schemas.UserSetting)
def update_user_setting(user_id: int, update: schemas.UserSettingUpdate, db: Session = Depends(get_db)):
    db_setting = db.query(models.UserSetting).filter(models.UserSetting.user_id == user_id).first()
    if not db_setting:
        raise HTTPException(status_code=404, detail="설정 없음")
    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_setting, field, value)
    db.commit()
    db.refresh(db_setting)
    return db_setting


