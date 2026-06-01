"""
Routers — FastAPI endpoints
============================
Organizado por domínio: auth, satellites, sensors, readings, alerts, dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token, hash_password, verify_password,
    get_current_user, get_admin_user,
)
from app.models.orm import UserORM
from app.repositories.repositories import (
    SatelliteRepository, SensorRepository,
    ReadingRepository, AlertRepository,
)
from app.schemas.schemas import (
    UserCreate, UserResponse, TokenResponse, LoginRequest,
    SatelliteCreate, SatelliteResponse,
    SensorCreate, SensorResponse,
    CloudReadingCreate, CloudReadingResponse,
    AlertResponse, AlertResolveRequest,
    DashboardSummary,
)
from app.services.service import CloudIdentifierService
import uuid


# ──────────────────────────────────────────────
# DI helper
# ──────────────────────────────────────────────

def get_service(db: Session = Depends(get_db)) -> CloudIdentifierService:
    return CloudIdentifierService(
        satellite_repo=SatelliteRepository(db),
        sensor_repo=SensorRepository(db),
        reading_repo=ReadingRepository(db),
        alert_repo=AlertRepository(db),
    )


# ──────────────────────────────────────────────
# Auth router
# ──────────────────────────────────────────────

router_auth = APIRouter(prefix="/auth", tags=["Autenticação"])


@router_auth.post("/register", response_model=UserResponse, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    """Registra novo usuário."""
    if db.query(UserORM).filter(UserORM.username == data.username).first():
        raise HTTPException(400, detail="Username já em uso")
    if db.query(UserORM).filter(UserORM.email == data.email).first():
        raise HTTPException(400, detail="E-mail já em uso")

    user = UserORM(
        id=str(uuid.uuid4()),
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router_auth.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Autentica e retorna JWT Bearer token."""
    user = db.query(UserORM).filter(UserORM.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )
    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token)


@router_auth.get("/me", response_model=UserResponse)
def me(current_user: UserORM = Depends(get_current_user)):
    """Retorna dados do usuário autenticado."""
    return current_user


# ──────────────────────────────────────────────
# Satellites router
# ──────────────────────────────────────────────

router_satellites = APIRouter(prefix="/satellites", tags=["Satélites"])


@router_satellites.get("/", response_model=list[SatelliteResponse])
def list_satellites(
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    return svc.list_satellites()


@router_satellites.post("/", response_model=SatelliteResponse, status_code=201)
def create_satellite(
    data: SatelliteCreate,
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    try:
        return svc.register_satellite(data)
    except Exception as exc:
        raise HTTPException(400, detail=str(exc)) from exc


# ──────────────────────────────────────────────
# Sensors router
# ──────────────────────────────────────────────

router_sensors = APIRouter(prefix="/sensors", tags=["Sensores"])


@router_sensors.get("/", response_model=list[SensorResponse])
def list_sensors(
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    return svc.list_sensors()


@router_sensors.post("/", response_model=SensorResponse, status_code=201)
def create_sensor(
    data: SensorCreate,
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    try:
        return svc.register_sensor(data)
    except Exception as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router_sensors.patch("/{sensor_id}/offline", status_code=204)
def mark_offline(
    sensor_id: str,
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    svc.mark_sensor_offline(sensor_id)


# ──────────────────────────────────────────────
# Readings router
# ──────────────────────────────────────────────

router_readings = APIRouter(prefix="/readings", tags=["Leituras"])


@router_readings.post("/", response_model=CloudReadingResponse, status_code=201)
def ingest_reading(
    data: CloudReadingCreate,
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    """Ingere uma nova leitura do pipeline OpenCV."""
    try:
        return svc.ingest_reading(data)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router_readings.get("/recent", response_model=list[CloudReadingResponse])
def recent_readings(
    limit: int = 20,
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    return svc.get_recent_readings(limit)


@router_readings.get("/sensor/{sensor_id}", response_model=list[CloudReadingResponse])
def readings_by_sensor(
    sensor_id: str,
    limit: int = 50,
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    return svc.get_readings_by_sensor(sensor_id, limit)


# ──────────────────────────────────────────────
# Alerts router
# ──────────────────────────────────────────────

router_alerts = APIRouter(prefix="/alerts", tags=["Alertas"])


@router_alerts.get("/", response_model=list[AlertResponse])
def active_alerts(
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    return svc.get_active_alerts()


@router_alerts.patch("/resolve", response_model=AlertResponse)
def resolve_alert(
    data: AlertResolveRequest,
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    try:
        return svc.resolve_alert(data.alert_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


# ──────────────────────────────────────────────
# Dashboard router
# ──────────────────────────────────────────────

router_dashboard = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router_dashboard.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    svc: CloudIdentifierService = Depends(get_service),
    _: UserORM = Depends(get_current_user),
):
    """Retorna sumário completo para o dashboard."""
    return svc.get_dashboard_summary()
