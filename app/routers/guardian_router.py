from fastapi import APIRouter, Response, status, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas, utils
from app.database import get_db
from pydantic import BaseModel

router = APIRouter(prefix="/guardians", tags=["Guardians"])

# 보호자 - 사용자 연결
class LinkUserByInfoRequest(BaseModel):
    guardian_id: int
    user_name: str
    user_phone_number: str
@router.post("/link/by-info", response_model=schemas.UserGuardianLinkResponse)
def link_user_by_info(request: LinkUserByInfoRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.name == request.user_name,
        models.User.phone_number == request.user_phone_number
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="해당 사용자 정보가 없습니다.")

    exist = db.query(models.UserGuardianLink).filter_by(
        guardian_id=request.guardian_id,
        user_id=user.user_id
    ).first()
    if exist:
        raise HTTPException(status_code=400, detail="이미 연결되어 있습니다.")

    link = models.UserGuardianLink(
        guardian_id=request.guardian_id,
        user_id=user.user_id
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    setting_exist = db.query(models.GuardianUserSetting).filter_by(
        guardian_id=request.guardian_id,
        user_id=user.user_id
    ).first()
    if not setting_exist:
        setting = models.GuardianUserSetting(
            guardian_id=request.guardian_id,
            user_id=user.user_id,
            low_sound_alert=True,
            battery_alert=True,
            disconnect_alert=True
        )
        db.add(setting)
        db.commit()

    return link

# 보호자의 사용자리스트
@router.get("/{guardian_id}/users", response_model=List[schemas.UserResponse])
def users_by_guardian(guardian_id: int, db: Session = Depends(get_db)):
    guardian = db.query(models.Guardian).filter_by(guardian_id=guardian_id).first()
    if not guardian:
        raise HTTPException(status_code=404, detail="보호자 정보가 없습니다.")

    user_responses = []
    for link in guardian.user_links:
        user = link.user
        user_data = schemas.UserResponse.from_orm(user)
        user_responses.append(user_data)

    return user_responses

@router.delete("/{guardian_id}/unlink/{user_id}")
def unlink_user(guardian_id: int, user_id: int, db: Session = Depends(get_db)):
    link = db.query(models.UserGuardianLink).filter_by(
        guardian_id=guardian_id, user_id=user_id
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="연결된 사용자가 없습니다.")
    db.delete(link)
    db.commit()
    return {"detail": "연결 해제 완료"}


@router.get("/0/users", include_in_schema=False)
def noop_guardian_zero():
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# 보호자 기본 CRUD
@router.get("/", response_model=List[schemas.GuardianResponse])
def get_all_guardians(db: Session = Depends(get_db)):
    return db.query(models.Guardian).all()

@router.get("/{guardian_id}", response_model=schemas.GuardianResponse)
def get_guardian(guardian_id: int, db: Session = Depends(get_db)):
    guardian = db.query(models.Guardian).filter(models.Guardian.guardian_id == guardian_id).first()
    if not guardian:
        raise HTTPException(status_code=404, detail="해당 보호자가 없습니다.")
    return guardian

@router.put("/{guardian_id}", response_model=schemas.GuardianResponse)
def update_guardian(guardian_id: int, update: schemas.GuardianCreate, db: Session = Depends(get_db)):
    guardian = db.query(models.Guardian).filter(models.Guardian.guardian_id == guardian_id).first()
    if not guardian:
        raise HTTPException(status_code=404, detail="해당 보호자가 없습니다.")
    guardian.name = update.name
    guardian.birth_date = update.birth_date
    guardian.phone_number = update.phone_number
    guardian.password = utils.hash_password(update.password)
    db.commit()
    db.refresh(guardian)
    return guardian

@router.delete("/{guardian_id}")
def delete_guardian(guardian_id: int, db: Session = Depends(get_db)):
    guardian = db.query(models.Guardian).filter(models.Guardian.guardian_id == guardian_id).first()
    if not guardian:
        raise HTTPException(status_code=404, detail="해당 보호자가 없습니다.")
    db.delete(guardian)
    db.commit()
    return {"보호자 삭제 완료"}

@router.post("/{guardian_id}/device-token")
def update_guardian_device_token(guardian_id: int, payload: schemas.DeviceTokenUpdate, db: Session = Depends(get_db)):
    guardian = db.query(models.Guardian).filter(models.Guardian.guardian_id == guardian_id).first()
    if not guardian:
        raise HTTPException(status_code=404, detail="해당 보호자가 없습니다.")

    guardian.device_token = payload.token
    db.commit()
    return {"message": "token 저장 완료"}