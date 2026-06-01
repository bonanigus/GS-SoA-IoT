"""
Repositories — Interfaces + Implementações
===========================================
Interface abstrata para cada repositório (testabilidade e DI).
Implementações concretas usam SQLAlchemy.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.orm import (
    SatelliteORM, SensorORM, CloudReadingORM, AlertORM, UserORM
)
from app.schemas.schemas import (
    SatelliteCreate, SensorCreate, CloudReadingCreate
)


# ──────────────────────────────────────────────
# Interfaces (contratos)
# ──────────────────────────────────────────────

class ISatelliteRepository(ABC):
    @abstractmethod
    def get_all(self) -> list[SatelliteORM]: ...
    @abstractmethod
    def get_by_id(self, satellite_id: str) -> Optional[SatelliteORM]: ...
    @abstractmethod
    def create(self, data: SatelliteCreate) -> SatelliteORM: ...
    @abstractmethod
    def delete(self, satellite_id: str) -> bool: ...


class ISensorRepository(ABC):
    @abstractmethod
    def get_all(self) -> list[SensorORM]: ...
    @abstractmethod
    def get_by_id(self, sensor_id: str) -> Optional[SensorORM]: ...
    @abstractmethod
    def create(self, data: SensorCreate) -> SensorORM: ...
    @abstractmethod
    def update_status(self, sensor_id: str, status: str) -> Optional[SensorORM]: ...


class IReadingRepository(ABC):
    @abstractmethod
    def create(self, data: CloudReadingCreate) -> CloudReadingORM: ...
    @abstractmethod
    def get_recent(self, limit: int) -> list[CloudReadingORM]: ...
    @abstractmethod
    def get_since(self, since: datetime) -> list[CloudReadingORM]: ...
    @abstractmethod
    def get_by_sensor(self, sensor_id: str, limit: int) -> list[CloudReadingORM]: ...
    @abstractmethod
    def class_distribution(self, hours: int) -> dict[str, int]: ...


class IAlertRepository(ABC):
    @abstractmethod
    def get_active(self) -> list[AlertORM]: ...
    @abstractmethod
    def create(self, alert_type: str, title: str, message: str,
               severity: str, sensor_id: str) -> AlertORM: ...
    @abstractmethod
    def resolve(self, alert_id: str) -> Optional[AlertORM]: ...


# ──────────────────────────────────────────────
# Implementações concretas
# ──────────────────────────────────────────────

class SatelliteRepository(ISatelliteRepository):

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self) -> list[SatelliteORM]:
        return self._db.query(SatelliteORM).all()

    def get_by_id(self, satellite_id: str) -> Optional[SatelliteORM]:
        return self._db.query(SatelliteORM).filter(
            SatelliteORM.id == satellite_id
        ).first()

    def create(self, data: SatelliteCreate) -> SatelliteORM:
        sat = SatelliteORM(
            id=str(uuid.uuid4()),
            name=data.name,
            norad_id=data.norad_id,
            orbit_altitude_km=data.orbit_altitude_km,
        )
        self._db.add(sat)
        self._db.commit()
        self._db.refresh(sat)
        return sat

    def delete(self, satellite_id: str) -> bool:
        sat = self.get_by_id(satellite_id)
        if not sat:
            return False
        self._db.delete(sat)
        self._db.commit()
        return True


class SensorRepository(ISensorRepository):

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all(self) -> list[SensorORM]:
        return self._db.query(SensorORM).all()

    def get_by_id(self, sensor_id: str) -> Optional[SensorORM]:
        return self._db.query(SensorORM).filter(
            SensorORM.id == sensor_id
        ).first()

    def create(self, data: SensorCreate) -> SensorORM:
        sensor = SensorORM(
            id=str(uuid.uuid4()),
            name=data.name,
            sensor_type=data.sensor_type,
            latitude=data.latitude,
            longitude=data.longitude,
            altitude_km=data.altitude_km,
            video_source=data.video_source,
            satellite_id=data.satellite_id,
        )
        self._db.add(sensor)
        self._db.commit()
        self._db.refresh(sensor)
        return sensor

    def update_status(self, sensor_id: str, status: str) -> Optional[SensorORM]:
        sensor = self.get_by_id(sensor_id)
        if not sensor:
            return None
        sensor.status = status
        self._db.commit()
        self._db.refresh(sensor)
        return sensor


class ReadingRepository(IReadingRepository):

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, data: CloudReadingCreate) -> CloudReadingORM:
        is_storm = (
            data.cloud_class == "Cumulonimbus" and data.confidence >= 0.70
        )
        reading = CloudReadingORM(
            id=str(uuid.uuid4()),
            sensor_id=data.sensor_id,
            cloud_class=data.cloud_class,
            confidence=data.confidence,
            coverage=data.coverage,
            texture_score=data.texture_score,
            edge_density=data.edge_density,
            is_storm_risk=is_storm,
        )
        self._db.add(reading)
        self._db.commit()
        self._db.refresh(reading)
        return reading

    def get_recent(self, limit: int = 20) -> list[CloudReadingORM]:
        return (
            self._db.query(CloudReadingORM)
            .order_by(CloudReadingORM.timestamp.desc())
            .limit(limit)
            .all()
        )

    def get_since(self, since: datetime) -> list[CloudReadingORM]:
        return (
            self._db.query(CloudReadingORM)
            .filter(CloudReadingORM.timestamp >= since)
            .order_by(CloudReadingORM.timestamp.desc())
            .all()
        )

    def get_by_sensor(self, sensor_id: str, limit: int = 50) -> list[CloudReadingORM]:
        return (
            self._db.query(CloudReadingORM)
            .filter(CloudReadingORM.sensor_id == sensor_id)
            .order_by(CloudReadingORM.timestamp.desc())
            .limit(limit)
            .all()
        )

    def class_distribution(self, hours: int = 24) -> dict[str, int]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = (
            self._db.query(CloudReadingORM.cloud_class)
            .filter(CloudReadingORM.timestamp >= since)
            .all()
        )
        dist: dict[str, int] = {}
        for (cls,) in rows:
            dist[cls] = dist.get(cls, 0) + 1
        return dist


class AlertRepository(IAlertRepository):

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_active(self) -> list[AlertORM]:
        return (
            self._db.query(AlertORM)
            .filter(AlertORM.resolved == False)  # noqa: E712
            .order_by(AlertORM.created_at.desc())
            .all()
        )

    def get_recent(self, limit: int = 10) -> list[AlertORM]:
        return (
            self._db.query(AlertORM)
            .order_by(AlertORM.created_at.desc())
            .limit(limit)
            .all()
        )

    def create(self, alert_type: str, title: str, message: str,
               severity: str, sensor_id: str) -> AlertORM:
        alert = AlertORM(
            id=str(uuid.uuid4()),
            alert_type=alert_type,
            title=title,
            message=message,
            severity=severity,
            sensor_id=sensor_id,
        )
        self._db.add(alert)
        self._db.commit()
        self._db.refresh(alert)
        return alert

    def resolve(self, alert_id: str) -> Optional[AlertORM]:
        alert = self._db.query(AlertORM).filter(AlertORM.id == alert_id).first()
        if not alert:
            return None
        alert.resolved    = True
        alert.resolved_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(alert)
        return alert
