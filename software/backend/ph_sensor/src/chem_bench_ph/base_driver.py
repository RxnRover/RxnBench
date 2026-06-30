"""Abstract base for I2C drivers."""
import time
from abc import ABC, abstractmethod


class AbstractI2CDriver(ABC):
    """Handles the basic send/receive pattern over I2C so subclasses don't repeat it."""

    def __init__(self, i2c_bus, address: int):
        self.i2c_bus = i2c_bus
        self.address = address

    def _send_command(self, cmd: str) -> None:
        """Write an ASCII command string to the device (e.g. 'R', 'Cal,mid,7.0')."""
        self.i2c_bus.write(self.address, cmd.encode('ascii'))

    def _read_response(self, num_bytes: int = 31, delay_ms: int = 900) -> str:
        """Wait delay_ms then read num_bytes from the device. delay_ms varies by command (see datasheet)."""
        time.sleep(delay_ms / 1000.0)
        raw = self.i2c_bus.read(self.address, num_bytes)
        return self._parse_response(raw)

    @abstractmethod
    def _parse_response(self, raw: bytes) -> str:
        """Subclasses decode the raw bytes into a usable string here."""
        ...
