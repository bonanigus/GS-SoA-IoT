"""
main.py — Entry point da API
==============================
FastAPI com:
  - CORS configurado
  - Swagger automático em /docs
  - Banco inicializado no startup
  - Admin padrão seed
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import create_tables, SessionLocal
from app.core.security import ensure_default_admin
from app.routers.routers import (
    router_auth, router_satellites, router_sensors,
    router_readings, router_alerts, router_dashboard,
)


# ──────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_tables()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
        _seed_demo_data(db)
    finally:
        db.close()
    yield
    # Shutdown (nada necessário para SQLite)


def _seed_demo_data(db) -> None:
    """Popula dados de demonstração se o banco estiver vazio."""
    import uuid
    from datetime import datetime, timedelta, timezone
    from app.models.orm import SatelliteORM, SensorORM, CloudReadingORM, AlertORM

    if db.query(SatelliteORM).count() > 0:
        return   # já foi seedado

    # Satélites
    iss = SatelliteORM(id=str(uuid.uuid4()), name="ISS", norad_id="25544",
                       orbit_altitude_km=408.0)
    terra = SatelliteORM(id=str(uuid.uuid4()), name="Terra", norad_id="25994",
                         orbit_altitude_km=705.0)
    db.add_all([iss, terra])
    db.flush()

    # Sensores
    sensors_data = [
        ("ISS-CAM-01", "cloud_vision", 51.6, 0.0, 408.0, iss.id),
        ("ISS-CAM-02", "cloud_vision", -30.0, -60.0, 408.0, iss.id),
        ("TERRA-MODIS", "cloud_vision", 0.0, 0.0, 705.0, terra.id),
    ]
    sensor_ids = []
    for name, stype, lat, lon, alt, sat_id in sensors_data:
        s = SensorORM(
            id=str(uuid.uuid4()), name=name, sensor_type=stype,
            latitude=lat, longitude=lon, altitude_km=alt,
            satellite_id=sat_id, status="online",
        )
        db.add(s)
        db.flush()
        sensor_ids.append(s.id)

    # Leituras dos últimos 2 dias
    import random
    classes = ["Cumulonimbus", "Cumulus", "Stratus", "Cirrus", "Clear Sky"]
    now = datetime.now(timezone.utc)
    readings = []
    for i in range(60):
        cls = random.choice(classes)
        conf = round(random.uniform(0.5, 0.97), 2)
        cov  = round(random.uniform(0.05, 0.90), 2)
        r = CloudReadingORM(
            id=str(uuid.uuid4()),
            sensor_id=random.choice(sensor_ids),
            cloud_class=cls,
            confidence=conf,
            coverage=cov,
            texture_score=round(random.uniform(2, 35), 1),
            edge_density=round(random.uniform(0.005, 0.12), 4),
            is_storm_risk=(cls == "Cumulonimbus" and conf >= 0.70),
            timestamp=now - timedelta(hours=random.uniform(0, 48)),
        )
        readings.append(r)
    db.add_all(readings)

    # Alerta demo
    storm_r = next((r for r in readings if r.is_storm_risk), None)
    if storm_r:
        alert = AlertORM(
            id=str(uuid.uuid4()),
            alert_type="storm",
            title="Tempestade detectada — demo",
            message="Formação Cumulonimbus detectada com alta confiança.",
            severity="critical",
            sensor_id=storm_r.sensor_id,
        )
        db.add(alert)

    db.commit()
    print("[seed] Dados de demonstração inseridos.")


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(
    title="Cloud Identifier API",
    description=(
        "API REST para o sistema de identificação de padrões de nuvens via ISS. "
        "Integra pipeline OpenCV com banco de dados e dashboard em tempo real."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — permite acesso do dashboard local e de qualquer origem em dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # em produção: restringir ao domínio do front
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(router_auth)
app.include_router(router_satellites)
app.include_router(router_sensors)
app.include_router(router_readings)
app.include_router(router_alerts)
app.include_router(router_dashboard)


@app.get("/", tags=["Root"])
def root():
    return {
        "project": "Cloud Identifier GS",
        "docs": "/docs",
        "redoc": "/redoc",
        "status": "online",
    }
