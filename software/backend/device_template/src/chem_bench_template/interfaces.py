"""
Hardware interface contract for this device.

Define the minimum set of methods the SiLA feature needs from the hardware.
The feature depends only on this Protocol - not on any concrete driver class.
This is the seam that makes mock testing and hardware swapping possible.

TODO: rename MyDeviceProtocol and replace the stub methods with your device's
      actual operations. Keep it minimal - only what feature.py calls.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MyDeviceProtocol(Protocol):
    """
    TODO: rename to e.g. ConductivitySensorProtocol, LiquidHandlerProtocol, etc.

    Add one method per hardware operation your SiLA feature needs.
    Return types should be plain Python types (float, str, bool, tuple) -
    not hardware-specific objects. The feature layer should never import
    anything from a concrete driver.
    """

    def read(self) -> float:
        """
        TODO: replace with your primary measurement method.
        e.g. read conductivity, read temperature, get liquid level, etc.
        """
        ...

    def do_action(self, parameter: float) -> None:
        """
        TODO: replace with a control operation, or remove if not needed.
        e.g. set_flow_rate, dispense, move_to_position, etc.
        """
        ...
