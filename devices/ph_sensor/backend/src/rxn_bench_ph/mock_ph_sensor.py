"""In-memory mock pH sensor for development without hardware."""
from rxn_bench_ph.base_sensor import SensorReading

import random

class MockPHSensor:
    """In-memory pH sensor mock returning random values in [1, 14]."""

    def __init__(self) -> None:
        """Start at the EZO's default 25 C temperature compensation."""
        self._temperature = 25.0

    def read(self) -> SensorReading:
        """Return a random pH reading."""
        value = random.uniform(1, 14)
        return SensorReading(value, unit="pH", sensor_id="mock_ph")

    def calibrate(self, point: str, value: float) -> None:
        """No-op calibration."""
        pass

    def slope(self) -> tuple[float, float]:
        """Return a nominal (99.7, 100.3) slope."""
        return (99.7, 100.3)

    def set_temperature(self, temp: float) -> None:
        """Store the temperature-compensation value (no hardware to update)."""
        self._temperature = temp

    def get_temperature(self) -> float:
        """Return the stored temperature-compensation value in degrees C."""
        return self._temperature
