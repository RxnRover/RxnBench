"""In-memory mock pH sensor for development without hardware."""
from chem_bench_ph.base_sensor import SensorReading

import random

class MockPHSensor:

    def read(self) -> SensorReading:
        value = random.uniform(1, 14) 
        return SensorReading(value, unit="pH", sensor_id="mock_ph")

    def calibrate(self, point: str, value: float) -> None:
        pass

    def slope(self) -> tuple[float, float]:
        return (99.7, 100.3)
