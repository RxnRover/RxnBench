"""Interface contract for pH sensors."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from rxn_bench_ph.base_sensor import SensorReading


@runtime_checkable
class PHSensorProtocol(Protocol):
    """Minimum interface required by the PHSensor SiLA feature."""

    def read(self) -> SensorReading:
        """Take a single measurement and return it as a SensorReading."""
        ...

    def calibrate(self, point: str, value: float) -> None:
        """Calibrate the probe at a known pH buffer."""
        ...

    def slope(self) -> tuple[float, float]:
        """Return (acid_pct, base_pct) slope percentages from the last calibration."""
        ...
