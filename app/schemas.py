from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class SoundTypeEnum(str, Enum):
    danger = "danger"
    help = "help"
    warning = "warning"

class StatusEnum(str, Enum):
    sent = "sent"
    pending = "pending"

class UserTypeEnum(str, Enum):
    user = "user"
    guardian = "guardian"

class UserBase(BaseModel):
    name: str
    birth_date: date
    phone_number: str
    face_image_url: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    user_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class GuardianBase(BaseModel):
    name: str
    birth_date: date
    phone_number: str

class GuardianCreate(GuardianBase):
    password: str

class GuardianResponse(GuardianBase):
    guardian_id: int
    created_at: datetime
    class Config:
        from_attributes = True

class UserGuardianLinkBase(BaseModel):
    user_id: int
    guardian_id: int

class UserGuardianLinkCreate(UserGuardianLinkBase):
    pass

class UserGuardianLinkResponse(UserGuardianLinkBase):
    link_id: int
    class Config:
        from_attributes = True

class GuardianUserSettingBase(BaseModel):
    low_sound_alert: bool = True
    battery_alert: bool = True
    disconnect_alert: bool = True


class GuardianUserSettingResponse(BaseModel):

    low_sound_alert: bool
    battery_alert: bool
    disconnect_alert: bool

    class Config:
        from_attributes = True

class GuardianUserSettingUpdate(BaseModel):
    low_sound_alert: bool
    battery_alert: bool
    disconnect_alert: bool

class SoundEventBase(BaseModel):
    sound_type: SoundTypeEnum
    sound_detail: Optional[str] = None
    angle: Optional[float] = None
    occurred_at: datetime
    sound_icon: Optional[str] = None
    location_image_url: Optional[str] = None
    decibel: Optional[float] = None

class SoundEventCreate(SoundEventBase):
    user_id: int

class SoundEventResponse(SoundEventBase):
    event_id: int
    user_id: int
    class Config:
        from_attributes = True

class PushNotificationBase(BaseModel):
    event_id: int
    user_id: int
    status: StatusEnum
    sent_at: datetime

class PushNotificationCreate(PushNotificationBase):
    pass

class PushNotificationResponse(PushNotificationBase):
    notification_id: int
    class Config:
        from_attributes = True

class UserSettingBase(BaseModel):
    low_sound_alert: bool = True
    battery_alert: bool = True
    disconnect_alert: bool = True

class UserSettingCreate(UserSettingBase):
    user_id: int

class UserSettingUpdate(UserSettingBase):
    pass

class UserSetting(UserSettingBase):
    setting_id: int
    user_id: int
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    user_type: UserTypeEnum
    phone_number: str
    password: str


class LoginResponse(BaseModel):
    message: str
    user_id: Optional[int] = None
    guardian_id: Optional[int] = None
    name: Optional[str] = None

class SignupRequest(BaseModel):
    name: str
    birth_date: date
    phone_number: str
    password: str
    password_check: str
    user_type: UserTypeEnum

class DeviceTokenUpdate(BaseModel):
    token: str

class LogoutRequest(BaseModel):
    user_type: UserTypeEnum
    user_id: Optional[int] = None
    guardian_id: Optional[int] = None

# SLAM
class SlamStartReq(BaseModel):
    save_map: bool
    map_name: str

class EnqueueResp(BaseModel):
    req_id: str

class Pose(BaseModel):
    x: float
    y: float
    theta: Optional[float] = None


class BatteryReport(BaseModel):
    device_id: Optional[str] = Field(None, description="장치 식별자(선택)")
    level: float = Field(..., ge=0, le=100, description="배터리 잔량 %")
    is_charging: Optional[bool] = Field(None, description="충전 중 여부")
    ts: Optional[datetime] = Field(None, description="측정 시각(없으면 서버가 now)")

    model_config = ConfigDict(json_schema_extra={
        "example": {"device_id":"robot-1","level":87.5,"is_charging":False}
    })


class CallEventBase(BaseModel):
    user_id: int

class CallEventCreate(CallEventBase):
    pass

class CallEventResponse(CallEventBase):
    call_id: int
    created_at: datetime

    class Config:
        orm_mode = True