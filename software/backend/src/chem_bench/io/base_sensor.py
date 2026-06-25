"""
Base classes shared by all sensors.

Author: John Brittain
Date: Jun 11 2026
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ------------------------------------
# Reading dataclass
# ------------------------------------

@dataclass
class SensorReading:
    """A single measurement bundled with metadata.

    Attributes
    ----------
    value : Any
        The measured value.
    unit : str
        Unit of the measurement (e.g. 'pH', 'mV').
    sensor_id : str
        Which sensor produced this reading.
    timestamp : datetime
        UTC time the reading was taken.
    """
    value: Any
    unit: str
    sensor_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ------------------------------------
# Base sensor
# ------------------------------------

class BaseSensor(ABC):
    """Abstract base every sensor class inherits from.

    Provides sensor identity (sensor_id, display_name, description) and
    enforces that all sensors are readable. Capability metadata is handled
    by the SiLA CDK layer (sila.Feature decorators), not here.

    Parameters
    ----------
    sensor_id : str
        Unique ID for this sensor instance (e.g. 'ph_sensor_1').

    Class Attributes
    ----------------
    display_name : str
        Human-readable name for this sensor type.
    description : str
        Short description of what the sensor measures.
    """

    display_name: str = 'Sensor'
    description: str = ''

    def __init__(self, sensor_id: str):
        self.sensor_id = sensor_id

    @abstractmethod
    def read(self) -> SensorReading: ...
