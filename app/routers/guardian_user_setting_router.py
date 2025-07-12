from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db

# 보호자와 연결된 사용자별 설정세팅
router = APIRouter(prefix="/guardian-user-settings", tags=["GuardianUserSetting"])

@router.get("/{guardian_id}/{user_id}", response_model=schemas.GuardianUserSettingResponse)
def get_setting(guardian_id: int, user_id: int, db: Session = Depends(get_db)):
    setting = db.query(models.GuardianUserSetting).filter_by(
        guardian_id=guardian_id, user_id=user_id
    ).first()
    if not setting:
        raise HTTPException(status_code=404, detail="설정 없음")
    return setting

@router.put("/{guardian_id}/{user_id}", response_model=schemas.GuardianUserSettingResponse)
def update_setting(
    guardian_id: int,
    user_id: int,
    update: schemas.GuardianUserSettingUpdate,
    db: Session = Depends(get_db)
):
    setting = db.query(models.GuardianUserSetting).filter_by(
        guardian_id=guardian_id, user_id=user_id
    ).first()
    if not setting:
        raise HTTPException(status_code=404, detail="설정 없음")
    for field, value in update.dict().items():
        setattr(setting, field, value)
    db.commit()
    db.refresh(setting)
    return setting
