"""Base classes shared by all sensors."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SensorReading:
    """A single measurement bundled with metadata."""
    value: Any
    unit: str
    sensor_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseSensor(ABC):
    """Abstract base every sensor class inherits from."""

    display_name: str = 'Sensor'
    description: str = ''

    def __init__(self, sensor_id: str):
        self.sensor_id = sensor_id

    @abstractmethod
    def read(self) -> SensorReading: ...
