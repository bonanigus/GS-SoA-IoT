"""
Domain Models — Cloud Identifier GS
=====================================
Modelagem de domínio com POO completo:
  - Classes Abstratas (Sensor, Alert)
  - Herança e Polimorfismo (CloudSensor, TemperatureSensor)
  - Classes públicas, privadas e estáticas
  - Value Objects (Coordinates, CloudReading)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────
# Enums de domínio
# ──────────────────────────────────────────────

class CloudClass(str, Enum):
    CUMULONIMBUS = "Cumulonimbus"
    CUMULUS      = "Cumulus"
    STRATUS      = "Stratus"
    CIRRUS       = "Cirrus"
    CLEAR_SKY    = "Clear Sky"
    UNKNOWN      = "Unknown"


class AlertSeverity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class SensorStatus(str, Enum):
    ONLINE   = "online"
    OFFLINE  = "offline"
    DEGRADED = "degraded"


# ──────────────────────────────────────────────
# Value Objects (imutáveis, sem identidade)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class Coordinates:
    """VO: posição geográfica de um satélite ou sensor."""
    latitude:  float
    longitude: float
    altitude_km: float = 0.0

    def __post_init__(self) -> None:
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Latitude inválida: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Longitude inválida: {self.longitude}")

    @staticmethod
    def iss_default() -> "Coordinates":
        """Coordenadas padrão aproximadas da ISS."""
        return Coordinates(latitude=51.6, longitude=0.0, altitude_km=408.0)


@dataclass(frozen=True)
class CloudReading:
    """VO: leitura pontual de análise de nuvem."""
    cloud_class:   CloudClass
    confidence:    float          # 0.0 – 1.0
    coverage:      float          # fração do frame
    texture_score: float
    edge_density:  float
    timestamp:     datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Confidence deve estar entre 0 e 1")
        if not (0.0 <= self.coverage <= 1.0):
            raise ValueError("Coverage deve estar entre 0 e 1")

    @property
    def is_storm_risk(self) -> bool:
        return (
            self.cloud_class == CloudClass.CUMULONIMBUS
            and self.confidence >= 0.70
        )


# ──────────────────────────────────────────────
# Classe Abstrata Base: Sensor
# ──────────────────────────────────────────────

class Sensor(ABC):
    """
    Classe abstrata base para todos os sensores do sistema.
    Define o contrato que subclasses devem implementar.
    """

    def __init__(self, name: str, location: Coordinates) -> None:
        self._id: str             = str(uuid.uuid4())
        self._name: str           = name
        self._location: Coordinates = location
        self._status: SensorStatus  = SensorStatus.ONLINE
        self.__created_at: datetime = datetime.now(timezone.utc)  # privado

    # ── Propriedades públicas ──────────────────

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def location(self) -> Coordinates:
        return self._location

    @property
    def status(self) -> SensorStatus:
        return self._status

    @property
    def created_at(self) -> datetime:
        return self.__created_at

    # ── Métodos abstratos (contrato) ───────────

    @abstractmethod
    def get_sensor_type(self) -> str:
        """Retorna o tipo do sensor como string."""
        ...

    @abstractmethod
    def validate_reading(self, reading: object) -> bool:
        """Valida se uma leitura é aceitável para este sensor."""
        ...

    # ── Métodos concretos ──────────────────────

    def set_status(self, status: SensorStatus) -> None:
        self._status = status

    def is_operational(self) -> bool:
        return self._status == SensorStatus.ONLINE

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self._id[:8]} name={self._name}>"


# ──────────────────────────────────────────────
# Subclasse: CloudSensor (herança + polimorfismo)
# ──────────────────────────────────────────────

class CloudSensor(Sensor):
    """
    Sensor de nuvens baseado em análise de vídeo (OpenCV).
    Herda de Sensor e implementa os métodos abstratos.
    """

    _instance_count: int = 0   # atributo estático de classe

    def __init__(self, name: str, location: Coordinates,
                 video_source: str = "0") -> None:
        super().__init__(name, location)
        self.video_source: str = video_source
        self._readings: list[CloudReading] = []
        CloudSensor._instance_count += 1

    # ── Polimorfismo ───────────────────────────

    def get_sensor_type(self) -> str:
        return "cloud_vision"

    def validate_reading(self, reading: object) -> bool:
        if not isinstance(reading, CloudReading):
            return False
        return 0.0 <= reading.confidence <= 1.0

    # ── Comportamento específico ───────────────

    def record_reading(self, reading: CloudReading) -> None:
        if not self.validate_reading(reading):
            raise ValueError(f"Leitura inválida para {self.name}")
        self._readings.append(reading)

    def get_latest_reading(self) -> Optional[CloudReading]:
        return self._readings[-1] if self._readings else None

    def get_readings_since(self, since: datetime) -> list[CloudReading]:
        return [r for r in self._readings if r.timestamp >= since]

    @staticmethod
    def get_instance_count() -> int:
        """Retorna quantos CloudSensors foram criados (estático)."""
        return CloudSensor._instance_count


class TemperatureSensor(Sensor):
    """
    Sensor de temperatura atmosférica.
    Herda de Sensor — demonstra polimorfismo com CloudSensor.
    """

    def __init__(self, name: str, location: Coordinates,
                 unit: str = "celsius") -> None:
        super().__init__(name, location)
        self.unit = unit
        self._temperature: Optional[float] = None

    def get_sensor_type(self) -> str:
        return "temperature"

    def validate_reading(self, reading: object) -> bool:
        if not isinstance(reading, (int, float)):
            return False
        return -100.0 <= float(reading) <= 60.0

    def record_temperature(self, value: float) -> None:
        if not self.validate_reading(value):
            raise ValueError(f"Temperatura fora do range: {value}")
        self._temperature = value

    @property
    def current_temperature(self) -> Optional[float]:
        return self._temperature


# ──────────────────────────────────────────────
# Classe Abstrata Base: Alert
# ──────────────────────────────────────────────

class Alert(ABC):
    """Classe abstrata para alertas do sistema."""

    def __init__(self, title: str, severity: AlertSeverity,
                 sensor_id: str) -> None:
        self._id:        str           = str(uuid.uuid4())
        self._title:     str           = title
        self._severity:  AlertSeverity = severity
        self._sensor_id: str           = sensor_id
        self._created_at: datetime     = datetime.now(timezone.utc)
        self._resolved:   bool         = False
        self._resolved_at: Optional[datetime] = None

    @property
    def id(self)         -> str:           return self._id
    @property
    def title(self)      -> str:           return self._title
    @property
    def severity(self)   -> AlertSeverity: return self._severity
    @property
    def sensor_id(self)  -> str:           return self._sensor_id
    @property
    def created_at(self) -> datetime:      return self._created_at
    @property
    def is_resolved(self) -> bool:         return self._resolved

    @abstractmethod
    def get_alert_type(self) -> str: ...

    @abstractmethod
    def get_message(self) -> str: ...

    def resolve(self) -> None:
        self._resolved    = True
        self._resolved_at = datetime.now(timezone.utc)

    def time_open(self) -> float:
        """Retorna segundos desde a criação do alerta."""
        end = self._resolved_at or datetime.now(timezone.utc)
        return (end - self._created_at).total_seconds()


class StormAlert(Alert):
    """Alerta específico para tempestades detectadas (Cumulonimbus)."""

    def __init__(self, sensor_id: str, confidence: float,
                 coverage: float) -> None:
        severity = AlertSeverity.CRITICAL if confidence >= 0.85 else AlertSeverity.HIGH
        super().__init__(
            title=f"Tempestade detectada — confiança {confidence:.0%}",
            severity=severity,
            sensor_id=sensor_id,
        )
        self.confidence = confidence
        self.coverage   = coverage

    def get_alert_type(self) -> str:
        return "storm"

    def get_message(self) -> str:
        return (
            f"Formação Cumulonimbus detectada com {self.confidence:.0%} de confiança. "
            f"Cobertura de nuvens: {self.coverage:.0%}. "
            f"Risco de tempestade severa."
        )


class SensorOfflineAlert(Alert):
    """Alerta de sensor offline."""

    def __init__(self, sensor_id: str, sensor_name: str) -> None:
        super().__init__(
            title=f"Sensor offline: {sensor_name}",
            severity=AlertSeverity.MEDIUM,
            sensor_id=sensor_id,
        )
        self.sensor_name = sensor_name

    def get_alert_type(self) -> str:
        return "sensor_offline"

    def get_message(self) -> str:
        return f"O sensor '{self.sensor_name}' está offline ou sem resposta."


# ──────────────────────────────────────────────
# Entidade: Satellite
# ──────────────────────────────────────────────

class Satellite:
    """Representa um satélite monitorado pelo sistema."""

    def __init__(self, name: str, norad_id: str,
                 orbit_altitude_km: float = 408.0) -> None:
        self.id:                str         = str(uuid.uuid4())
        self.name:              str         = name
        self.norad_id:          str         = norad_id
        self.orbit_altitude_km: float       = orbit_altitude_km
        self._sensors:          list[Sensor] = []
        self._position:         Optional[Coordinates] = None
        self._last_contact:     Optional[datetime]    = None

    def attach_sensor(self, sensor: Sensor) -> None:
        self._sensors.append(sensor)

    def update_position(self, coords: Coordinates) -> None:
        self._position     = coords
        self._last_contact = datetime.now(timezone.utc)

    @property
    def position(self) -> Optional[Coordinates]:
        return self._position

    @property
    def sensors(self) -> list[Sensor]:
        return list(self._sensors)

    @property
    def last_contact(self) -> Optional[datetime]:
        return self._last_contact

    def get_cloud_sensors(self) -> list[CloudSensor]:
        return [s for s in self._sensors if isinstance(s, CloudSensor)]

    @staticmethod
    def iss() -> "Satellite":
        """Factory para a ISS."""
        sat = Satellite("ISS", "25544", orbit_altitude_km=408.0)
        sensor = CloudSensor(
            name="ISS-CAM-01",
            location=Coordinates.iss_default(),
            video_source="0",
        )
        sat.attach_sensor(sensor)
        sat.update_position(Coordinates.iss_default())
        return sat
