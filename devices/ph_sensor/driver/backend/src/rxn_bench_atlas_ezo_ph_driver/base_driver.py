"""Abstract base for I2C drivers."""
import time
from abc import ABC, abstractmethod


class AbstractI2CDriver(ABC):
    """Handles the basic send/receive pattern over I2C so subclasses don't repeat it."""

    # Bytes to read back per response. EZO replies are short (status byte +
    # a comma-separated ASCII payload); 31 covers every command's reply and
    # is never varied, so it's a constant rather than a per-call argument -
    # keeping _read_response's signature compatible with EZOCommandSet's hook.
    _RESPONSE_NUM_BYTES = 31

    def __init__(self, i2c_bus, address: int):
        """
        Args:
            i2c_bus: Open SMBus (or compatible) object for the I2C bus.
            address: 7-bit I2C address of the target device.
        """
        self.i2c_bus = i2c_bus
        self.address = address

    def _send_command(self, cmd: str) -> None:
        """Write an ASCII command string to the device (e.g. 'R', 'Cal,mid,7.0')."""
        self.i2c_bus.write(self.address, cmd.encode('ascii'))

    def _read_response(self, delay_ms: int = 900) -> str:
        """Wait delay_ms then read the reply. delay_ms varies by command (see datasheet)."""
        time.sleep(delay_ms / 1000.0)
        raw = self.i2c_bus.read(self.address, self._RESPONSE_NUM_BYTES)
        return self._parse_response(raw)

    @abstractmethod
    def _parse_response(self, raw: bytes) -> str:
        """Decode raw I2C bytes into a string. Subclasses check the status byte."""
        ...
