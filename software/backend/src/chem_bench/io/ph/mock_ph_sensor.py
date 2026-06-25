"""
In-memory mock pH sensor for development without hardware.

Satisfies PHSensorProtocol.  Returns a fixed pH of 7.00 and accepts
calibration calls as no-ops.  Use CHEM_BENCH_MOCK=1 to activate.

Author: John Brittain
Date: Jun 2026
"""
from chem_bench.io.base_sensor import SensorReading


class MockPHSensor:

    def read(self) -> SensorReading:
        return SensorReading(value=7.00, unit="pH", sensor_id="mock_ph")

    def calibrate(self, point: str, value: float) -> None:
        pass

    def slope(self) -> tuple[float, float]:
        return (99.7, 100.3)
