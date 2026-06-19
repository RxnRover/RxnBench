"""
Base classes and metadata shared by all sensors.

Author: John Brittain
Date: Jun 11 2026
"""
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ------------------------------------
# Metadata 
# ------------------------------------

def command(display_name: str, description: str = ''):
    """Tag a method as an invokable command (shows up in manifest/SiLA).

    Parameters
    ----------
    display_name : str
        Name shown in the UI or SiLA feature list.
    description : str, optional
        One-liner on what it does.
    """
    def decorator(func):
        func._is_command = True
        func._display_name = display_name
        func._description = description
        return func
    return decorator


def observable(display_name: str, unit: str, description: str = ''):
    """Tag a method as a readable data source (shows up in manifest/SiLA).

    Parameters
    ----------
    display_name : str
        Name shown in the UI or SiLA feature list.
    unit : str
        Unit of the value being returned (e.g. 'pH', 'mV', 'C').
    description : str, optional
        One-liner on what's being measured.
    """
    def decorator(func):
        func._is_observable = True
        func._display_name = display_name
        func._unit = unit
        func._description = description
        return func
    return decorator


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

    @abstractmethod
    def calibrate(self, *args, **kwargs) -> None: ...

    @abstractmethod
    def status(self) -> dict: ...

    def manifest(self) -> dict:
        """Return everything about this sensor: who it is, what it can do, what it publishes.

        Used to advertise the sensor to a UI, SiLA server, or anything else
        that needs to know the sensor's interface without hardcoding it.

        Returns
        -------
        dict
            Keys: ``sensor_id``, ``display_name``, ``description``,
            ``commands``, ``observables``.
        """
        commands = {}
        observables = {}

        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(method, '_is_command', False):
                commands[name] = {
                    'display_name': method._display_name,
                    'description': method._description,
                }
            if getattr(method, '_is_observable', False):
                observables[name] = {
                    'display_name': method._display_name,
                    'unit': method._unit,
                    'description': method._description,
                }

        return {
            'sensor_id': self.sensor_id,
            'display_name': self.__class__.display_name,
            'description': self.__class__.description,
            'commands': commands,
            'observables': observables,
        }
