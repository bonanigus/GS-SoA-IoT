"""
Services — Camada de negócio
==============================
Orquestra repositórios e aplica regras de negócio.
Usa Injeção de Dependência (recebe interfaces, não concretos).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.domain import (
    CloudClass, AlertSeverity, StormAlert, SensorOfflineAlert
)
from app.repositories.repositories import (
    ISatelliteRepository, ISensorRepository,
    IReadingRepository, IAlertRepository,
)
from app.schemas.schemas import (
    SatelliteCreate, SensorCreate, CloudReadingCreate,
    DashboardSummary, CloudReadingResponse, AlertResponse,
    SatelliteResponse, SensorResponse,
)


class CloudIdentifierService:
    """
    Serviço principal do sistema.
    Recebe repositórios via injeção de dependência (DI).
    """

    def __init__(
        self,
        satellite_repo: ISatelliteRepository,
        sensor_repo:    ISensorRepository,
        reading_repo:   IReadingRepository,
        alert_repo:     IAlertRepository,
    ) -> None:
        self._satellites = satellite_repo
        self._sensors    = sensor_repo
        self._readings   = reading_repo
        self._alerts     = alert_repo

    # ── Satélites ──────────────────────────────

    def list_satellites(self) -> list:
        return self._satellites.get_all()

    def register_satellite(self, data: SatelliteCreate):
        return self._satellites.create(data)

    # ── Sensores ───────────────────────────────

    def list_sensors(self) -> list:
        return self._sensors.get_all()

    def register_sensor(self, data: SensorCreate):
        return self._sensors.create(data)

    def mark_sensor_offline(self, sensor_id: str) -> None:
        sensor = self._sensors.update_status(sensor_id, "offline")
        if sensor:
            alert = SensorOfflineAlert(sensor_id=sensor_id, sensor_name=sensor.name)
            self._alerts.create(
                alert_type=alert.get_alert_type(),
                title=alert.title,
                message=alert.get_message(),
                severity=alert.severity,
                sensor_id=sensor_id,
            )

    # ── Leituras ───────────────────────────────

    def ingest_reading(self, data: CloudReadingCreate):
        """
        Persiste uma nova leitura e avalia se gera alerta.
        Regra: Cumulonimbus com confiança >= 0.70 → StormAlert.
        """
        reading = self._readings.create(data)

        if reading.is_storm_risk:
            storm = StormAlert(
                sensor_id=data.sensor_id,
                confidence=data.confidence,
                coverage=data.coverage,
            )
            self._alerts.create(
                alert_type=storm.get_alert_type(),
                title=storm.title,
                message=storm.get_message(),
                severity=storm.severity,
                sensor_id=data.sensor_id,
            )

        return reading

    def get_readings_by_sensor(self, sensor_id: str, limit: int = 50):
        return self._readings.get_by_sensor(sensor_id, limit)

    def get_recent_readings(self, limit: int = 20):
        return self._readings.get_recent(limit)

    # ── Alertas ────────────────────────────────

    def get_active_alerts(self):
        return self._alerts.get_active()

    def resolve_alert(self, alert_id: str):
        resolved = self._alerts.resolve(alert_id)
        if not resolved:
            raise ValueError(f"Alerta não encontrado: {alert_id}")
        return resolved

    # ── Dashboard ──────────────────────────────

    def get_dashboard_summary(self) -> DashboardSummary:
        sensors      = self._sensors.get_all()
        since_24h    = datetime.now(timezone.utc) - timedelta(hours=24)
        readings_24h = self._readings.get_since(since_24h)
        active_alerts = self._alerts.get_active()

        storm_count = sum(1 for a in active_alerts if a.alert_type == "storm")
        online_count = sum(1 for s in sensors if s.status == "online")

        latest_readings = self._readings.get_recent(limit=10)
        recent_alerts   = self._alerts.get_recent(limit=5) if hasattr(self._alerts, "get_recent") else active_alerts[:5]

        return DashboardSummary(
            total_sensors=len(sensors),
            online_sensors=online_count,
            total_readings_24h=len(readings_24h),
            active_alerts=len(active_alerts),
            storm_alerts=storm_count,
            class_distribution=self._readings.class_distribution(hours=24),
            latest_readings=[CloudReadingResponse.model_validate(r) for r in latest_readings],
            recent_alerts=[AlertResponse.model_validate(a) for a in recent_alerts],
        )
