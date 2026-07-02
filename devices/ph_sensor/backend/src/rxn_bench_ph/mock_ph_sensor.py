"""In-memory mock pH sensor for development without hardware."""
from rxn_bench_ph.base_sensor import SensorReading

import random

class MockPHSensor:
    """In-memory pH sensor mock returning random values in [1, 14]."""

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
