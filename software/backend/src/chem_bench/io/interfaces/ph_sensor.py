"""
Interface contract for pH sensors.

PHSensorProtocol defines the surface the PHSensor SiLA feature depends on.
AtlasPHSensor satisfies this structurally — no inheritance change needed.
Any future pH probe implementation only needs to match these three methods.

Author: John Brittain
Date: Jun 18 2026
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from chem_bench.io.base_sensor import SensorReading


@runtime_checkable
class PHSensorProtocol(Protocol):
    """Minimum interface required by the PHSensor SiLA feature.

    Implemented by AtlasPHSensor. A future probe (different chip, USB bridge,
    network sensor) only needs to satisfy these three methods to be registered
    as a pH feature without any changes to the feature code.
    """

    def read(self) -> SensorReading: ...

    def calibrate(self, point: str, value: float) -> None: ...

    def slope(self) -> tuple[float, float]: ...
