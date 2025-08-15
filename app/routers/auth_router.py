from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas, utils
from app.database import get_db
from datetime import datetime
from fastapi import Query

router = APIRouter(prefix="/auth", tags=["Auth"])
@router.post("/signup")
def unified_signup(data: schemas.SignupRequest, db: Session = Depends(get_db)):

    if data.password != data.password_check:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    name = data.name
    birth_date = data.birth_date
    phone = data.phone_number
    password = utils.hash_password(data.password)

    if data.user_type == schemas.UserTypeEnum.user:
        exists = db.query(models.User).filter(models.User.phone_number == phone).first()
        if exists:
            raise HTTPException(status_code=400, detail="이미 등록된 사용자 연락처입니다.")
        user = models.User(
            name=name,
            birth_date=birth_date,
            phone_number=phone,
            password=password,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        user_setting = models.UserSetting(
            user_id=user.user_id,
            low_sound_alert=True,
            battery_alert=True,
            disconnect_alert=True
        )
        db.add(user_setting)
        db.commit()

        return {"message": "사용자 회원가입 완료", "user_id": user.user_id}

    elif data.user_type == schemas.UserTypeEnum.guardian:
        exists = db.query(models.Guardian).filter(models.Guardian.phone_number == phone).first()
        if exists:
            raise HTTPException(status_code=400, detail="이미 등록된 보호자 연락처입니다.")
        guardian = models.Guardian(
            name=name,
            birth_date=birth_date,
            phone_number=phone,
            password=password,
            created_at=datetime.utcnow()
        )
        db.add(guardian)
        db.commit()
        db.refresh(guardian)
        return {"message": "보호자 회원가입 완료", "guardian_id": guardian.guardian_id}

    raise HTTPException(status_code=400, detail="잘못된 user_type입니다.")

# 같은 기기에서 로그인-로그아웃 여러번 하는 것에 따른 수정사항
@router.put("/device-token")
def update_device_token(
    data: schemas.DeviceTokenUpdate,
    user_type: schemas.UserTypeEnum = Query(...),
    user_id: int | None = Query(None),
    guardian_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    token = data.token
    if not token:
        raise HTTPException(status_code=400, detail="빈 토큰")

    db.query(models.User).filter(models.User.device_token == token).update({"device_token": None})
    db.query(models.Guardian).filter(models.Guardian.device_token == token).update({"device_token": None})

    if user_type == schemas.UserTypeEnum.user:
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id 필요")
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="사용자 없음")
        user.device_token = token

    elif user_type == schemas.UserTypeEnum.guardian:
        if not guardian_id:
            raise HTTPException(status_code=400, detail="guardian_id 필요")
        g = db.query(models.Guardian).filter(models.Guardian.guardian_id == guardian_id).first()
        if not g:
            raise HTTPException(status_code=404, detail="보호자 없음")
        g.device_token = token
    else:
        raise HTTPException(status_code=400, detail="잘못된 user_type")

    db.commit()
    return {"ok": True}

@router.post("/login", response_model=schemas.LoginResponse)
def login(login_data: schemas.LoginRequest, db: Session = Depends(get_db)):
    if login_data.user_type == schemas.UserTypeEnum.user:
        user = db.query(models.User).filter(models.User.phone_number == login_data.phone_number).first()
        if not user or not utils.verify_password(login_data.password, user.password):
            raise HTTPException(status_code=401, detail="사용자 정보가 올바르지 않습니다.")
        return schemas.LoginResponse(message="사용자 로그인 성공", user_id=user.user_id, name=user.name)
    elif login_data.user_type == schemas.UserTypeEnum.guardian:
        guardian = db.query(models.Guardian).filter(models.Guardian.phone_number == login_data.phone_number).first()
        if not guardian or not utils.verify_password(login_data.password, guardian.password):
            raise HTTPException(status_code=401, detail="보호자 정보가 올바르지 않습니다.")
        return schemas.LoginResponse(message="보호자 로그인 성공", guardian_id=guardian.guardian_id, name=guardian.name)
    raise HTTPException(status_code=400, detail="잘못된 user_type입니다.")

@router.post("/logout")
def logout(req: schemas.LogoutRequest, db: Session = Depends(get_db)):
    if req.user_type == schemas.UserTypeEnum.user and req.user_id:
        db.query(models.User).filter(models.User.user_id == req.user_id).update({"device_token": None})
    elif req.user_type == schemas.UserTypeEnum.guardian and req.guardian_id:
        db.query(models.Guardian).filter(models.Guardian.guardian_id == req.guardian_id).update({"device_token": None})
    else:
        raise HTTPException(status_code=400, detail="잘못된 요청")
    db.commit()
    return {"ok": True}