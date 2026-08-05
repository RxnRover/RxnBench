"""SMBus adapter exposing the simple write/read bus interface the drivers use.

AbstractI2CDriver talks to the bus through two methods:
    write(address, data: bytes)  - send raw bytes to the device
    read(address, n) -> bytes    - read n raw bytes from the device
"""
from __future__ import annotations


class SMBusI2C:
    """Raw-I2C adapter over an open smbus2.SMBus, for EZO-style byte streams."""

    def __init__(self, bus) -> None:
        """
        Args:
            bus: Open ``smbus2.SMBus`` instance (e.g. ``SMBus(1)`` on a Raspberry Pi).
        """
        self._bus = bus

    def write(self, address: int, data: bytes) -> None:
        """Write raw bytes to the device at *address*."""
        from smbus2 import i2c_msg
        self._bus.i2c_rdwr(i2c_msg.write(address, data))

    def read(self, address: int, num_bytes: int) -> bytes:
        """Read *num_bytes* raw bytes from the device at *address*."""
        from smbus2 import i2c_msg
        msg = i2c_msg.read(address, num_bytes)
        self._bus.i2c_rdwr(msg)
        return bytes(msg)

    def close(self) -> None:
        """Close the underlying SMBus."""
        self._bus.close()
