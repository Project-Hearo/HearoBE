from pydantic import BaseModel, Field
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
    user_type: UserTypeEnum
    face_image_url: Optional[str] = None  # user만 사용할 예정