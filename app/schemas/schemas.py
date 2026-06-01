"""
Schemas (DTOs) — Pydantic v2
==============================
Request / Response objects para a API.
Separados das entidades ORM (desacoplamento).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email:    str = Field(..., pattern=r"^[\w\.\-]+@[\w\-]+\.[a-z]{2,}$")
    password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:         str
    username:   str
    email:      str
    is_active:  bool
    is_admin:   bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


# ──────────────────────────────────────────────
# Satellite DTOs
# ──────────────────────────────────────────────

class SatelliteCreate(BaseModel):
    name:              str   = Field(..., min_length=1, max_length=100)
    norad_id:          str   = Field(..., min_length=1, max_length=20)
    orbit_altitude_km: float = Field(408.0, ge=200.0, le=50000.0)


class SatelliteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                str
    name:              str
    norad_id:          str
    orbit_altitude_km: float
    created_at:        datetime


# ──────────────────────────────────────────────
# Sensor DTOs
# ──────────────────────────────────────────────

class SensorCreate(BaseModel):
    name:         str   = Field(..., min_length=1, max_length=100)
    sensor_type:  str   = Field("cloud_vision")
    latitude:     float = Field(..., ge=-90.0, le=90.0)
    longitude:    float = Field(..., ge=-180.0, le=180.0)
    altitude_km:  float = Field(0.0, ge=0.0)
    video_source: str   = Field("0")
    satellite_id: Optional[str] = None


class SensorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:           str
    name:         str
    sensor_type:  str
    status:       str
    latitude:     float
    longitude:    float
    altitude_km:  float
    video_source: str
    satellite_id: Optional[str]
    created_at:   datetime


# ──────────────────────────────────────────────
# CloudReading DTOs
# ──────────────────────────────────────────────

class CloudReadingCreate(BaseModel):
    sensor_id:     str
    cloud_class:   str
    confidence:    float = Field(..., ge=0.0, le=1.0)
    coverage:      float = Field(..., ge=0.0, le=1.0)
    texture_score: float = Field(0.0)
    edge_density:  float = Field(0.0)

    @field_validator("cloud_class")
    @classmethod
    def validate_cloud_class(cls, v: str) -> str:
        valid = {"Cumulonimbus", "Cumulus", "Stratus", "Cirrus", "Clear Sky", "Unknown"}
        if v not in valid:
            raise ValueError(f"cloud_class deve ser um de: {valid}")
        return v


class CloudReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:            str
    sensor_id:     str
    cloud_class:   str
    confidence:    float
    coverage:      float
    texture_score: float
    edge_density:  float
    is_storm_risk: bool
    timestamp:     datetime


# ──────────────────────────────────────────────
# Alert DTOs
# ──────────────────────────────────────────────

class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:          str
    alert_type:  str
    title:       str
    message:     str
    severity:    str
    sensor_id:   str
    resolved:    bool
    created_at:  datetime
    resolved_at: Optional[datetime]


class AlertResolveRequest(BaseModel):
    alert_id: str


# ──────────────────────────────────────────────
# Dashboard summary DTO
# ──────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_sensors:       int
    online_sensors:      int
    total_readings_24h:  int
    active_alerts:       int
    storm_alerts:        int
    class_distribution:  dict[str, int]
    latest_readings:     list[CloudReadingResponse]
    recent_alerts:       list[AlertResponse]
