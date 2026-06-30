"""Interface contract for pH sensors."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from chem_bench_ph.base_sensor import SensorReading


@runtime_checkable
class PHSensorProtocol(Protocol):
    """Minimum interface required by the PHSensor SiLA feature."""

    def read(self) -> SensorReading: ...

    def calibrate(self, point: str, value: float) -> None: ...

    def slope(self) -> tuple[float, float]: ...
