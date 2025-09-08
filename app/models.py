from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Enum as SqlEnum, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
import enum

class SoundTypeEnum(str, enum.Enum):
    danger = "danger"
    help = "help"
    warning = "warning"

class StatusEnum(str, enum.Enum):
    sent = "sent"
    pending = "pending"

class UserTypeEnum(str, enum.Enum):
    user = "user"
    guardian = "guardian"

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    birth_date = Column(Date, nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sound_events = relationship("SoundEvent", back_populates="user", cascade="all, delete")
    notifications = relationship("PushNotification", back_populates="user", cascade="all, delete")
    guardian_links = relationship("UserGuardianLink", back_populates="user", cascade="all, delete")
    guardian_settings = relationship("GuardianUserSetting", back_populates="user", cascade="all, delete")
    settings = relationship("UserSetting", back_populates="user", uselist=False, cascade="all, delete")

    device_token = Column(String(255), nullable=True)
    call_events = relationship("CallEvent", back_populates="user", cascade="all, delete")

class Guardian(Base):
    __tablename__ = "guardians"

    guardian_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    birth_date = Column(Date, nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_links = relationship("UserGuardianLink", back_populates="guardian", cascade="all, delete")
    guardian_settings = relationship("GuardianUserSetting", back_populates="guardian", cascade="all, delete")

    device_token = Column(String(255), nullable=True)

class UserGuardianLink(Base):
    __tablename__ = "user_guardian_links"

    link_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    guardian_id = Column(Integer, ForeignKey("guardians.guardian_id"), nullable=False)

    user = relationship("User", back_populates="guardian_links")
    guardian = relationship("Guardian", back_populates="user_links")

class GuardianUserSetting(Base):
    __tablename__ = "guardian_user_settings"

    setting_id = Column(Integer, primary_key=True, index=True)
    guardian_id = Column(Integer, ForeignKey("guardians.guardian_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    low_sound_alert = Column(Boolean, default=True)
    battery_alert = Column(Boolean, default=True)
    disconnect_alert = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    guardian = relationship("Guardian", back_populates="guardian_settings")
    user = relationship("User", back_populates="guardian_settings")

class UserSetting(Base):
    __tablename__ = "user_settings"

    setting_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    low_sound_alert = Column(Boolean, default=True)
    battery_alert = Column(Boolean, default=True)
    disconnect_alert = Column(Boolean, default=True)

    user = relationship("User", back_populates="settings")


class SoundEvent(Base):
    __tablename__ = "sound_events"

    event_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    sound_type = Column(SqlEnum(SoundTypeEnum), nullable=False)
    sound_detail = Column(String(255))
    angle = Column(Float)
    occurred_at = Column(DateTime, nullable=False)
    sound_icon = Column(String(255), nullable=True)
    location_image_url = Column(String(255), nullable=True)
    decibel = Column(Float, nullable=True)

    user = relationship("User", back_populates="sound_events")
    notifications = relationship("PushNotification", back_populates="event", cascade="all, delete")  # ✅ cascade 추가


class PushNotification(Base):
    __tablename__ = "push_notifications"

    notification_id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("sound_events.event_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    status = Column(SqlEnum(StatusEnum), nullable=False)
    sent_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="notifications")
    event = relationship("SoundEvent", back_populates="notifications")

class CallEvent(Base):
    __tablename__ = "call_events"

    call_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="call_events")