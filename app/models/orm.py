"""
ORM Models — SQLAlchemy
========================
Entidades persistidas no banco SQLite.
Separadas dos domain models por responsabilidade (camada de infra).
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SatelliteORM(Base):
    __tablename__ = "satellites"

    id                 = Column(String(36), primary_key=True)
    name               = Column(String(100), nullable=False)
    norad_id           = Column(String(20), unique=True, nullable=False)
    orbit_altitude_km  = Column(Float, default=408.0)
    created_at         = Column(DateTime, default=_utcnow)

    sensors = relationship("SensorORM", back_populates="satellite",
                           cascade="all, delete-orphan")


class SensorORM(Base):
    __tablename__ = "sensors"

    id           = Column(String(36), primary_key=True)
    name         = Column(String(100), nullable=False)
    sensor_type  = Column(String(50), nullable=False)
    status       = Column(String(20), default="online")
    latitude     = Column(Float, nullable=False)
    longitude    = Column(Float, nullable=False)
    altitude_km  = Column(Float, default=0.0)
    video_source = Column(String(200), default="0")
    satellite_id = Column(String(36), ForeignKey("satellites.id"), nullable=True)
    created_at   = Column(DateTime, default=_utcnow)

    satellite = relationship("SatelliteORM", back_populates="sensors")
    readings  = relationship("CloudReadingORM", back_populates="sensor",
                             cascade="all, delete-orphan")


class CloudReadingORM(Base):
    __tablename__ = "cloud_readings"

    id            = Column(String(36), primary_key=True)
    sensor_id     = Column(String(36), ForeignKey("sensors.id"), nullable=False)
    cloud_class   = Column(String(50), nullable=False)
    confidence    = Column(Float, nullable=False)
    coverage      = Column(Float, nullable=False)
    texture_score = Column(Float, default=0.0)
    edge_density  = Column(Float, default=0.0)
    is_storm_risk = Column(Boolean, default=False)
    timestamp     = Column(DateTime, default=_utcnow, index=True)

    sensor = relationship("SensorORM", back_populates="readings")


class AlertORM(Base):
    __tablename__ = "alerts"

    id          = Column(String(36), primary_key=True)
    alert_type  = Column(String(50), nullable=False)
    title       = Column(String(200), nullable=False)
    message     = Column(Text, nullable=False)
    severity    = Column(String(20), nullable=False)
    sensor_id   = Column(String(36), ForeignKey("sensors.id"), nullable=False)
    resolved    = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=_utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)


class UserORM(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True)
    username      = Column(String(50), unique=True, nullable=False)
    email         = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    is_active     = Column(Boolean, default=True)
    is_admin      = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=_utcnow)
