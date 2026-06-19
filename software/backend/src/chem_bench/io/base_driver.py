"""
Abstract base for I2C drivers.

Author: John Brittain
Date: Jun 11 2026
"""
import time
from abc import ABC, abstractmethod


class AbstractI2CDriver(ABC):
    """Handles the basic send/receive pattern over I2C so subclasses don't repeat it.

    Parameters
    ----------
    i2c_bus :
        Bus object with ``read(address, n_bytes)`` and ``write(address, data)``.
    address : int
        I2C address of the device.
    """

    def __init__(self, i2c_bus, address: int):
        self.i2c_bus = i2c_bus
        self.address = address

    def _send_command(self, cmd: str) -> None:
        """Write an ASCII command string to the device.

        Parameters
        ----------
        cmd : str
            Command to send (e.g. 'R', 'Cal,mid,7.0').
        """
        self.i2c_bus.write(self.address, cmd.encode('ascii'))

    def _read_response(self, num_bytes: int = 31, delay_ms: int = 900) -> str:
        """Wait for the device to process, then read and parse the response.

        Parameters
        ----------
        num_bytes : int, optional
            How many bytes to read back.
        delay_ms : int, optional
            How long to wait before reading. Varies by command, check the datasheet.

        Returns
        -------
        str
            Parsed response string.
        """
        time.sleep(delay_ms / 1000.0)
        raw = self.i2c_bus.read(self.address, num_bytes)
        return self._parse_response(raw)

    @abstractmethod
    def _parse_response(self, raw: bytes) -> str:
        """Subclasses decode the raw bytes into a usable string here."""
        ...
