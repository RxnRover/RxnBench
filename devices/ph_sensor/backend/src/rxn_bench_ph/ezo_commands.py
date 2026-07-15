"""Transport-agnostic Atlas Scientific EZO-pH command set.

The EZO command protocol (``R``, ``Cal,mid,7.0``, ``Slope,?``, ...) is identical
whether the circuit is spoken to over I2C or UART - only the byte-level
send/receive differs. This mixin holds those commands once so the I2C driver
(:class:`~rxn_bench_ph.atlas_scientific_driver.AtlasScientificEZO`) and the UART
driver (:class:`~rxn_bench_ph.atlas_scientific_uart_driver.AtlasScientificEZOUart`)
share them instead of each maintaining a drifting copy.

Concrete drivers provide the two transport hooks:

    _send_command(cmd)          - put an ASCII command on the wire
    _read_response(delay_ms)    - return the device's ASCII reply as a string

For I2C that means writing bytes then reading back a status-byte-prefixed
payload; for UART it means writing ``cmd\\r`` then reading a CR-terminated line.
Either way ``_read_response`` returns the already-decoded payload string (empty
for ack-only commands), so the command methods below never see transport bytes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EZOCommandSet(ABC):
    """The EZO-pH command protocol, independent of the underlying transport."""

    @abstractmethod
    def _send_command(self, cmd: str) -> None:
        """Write an ASCII command string to the device (e.g. 'R', 'Cal,mid,7.0')."""
        ...

    @abstractmethod
    def _read_response(self, delay_ms: int = 900) -> str:
        """Return the device's decoded ASCII reply. delay_ms varies by command (see datasheet)."""
        ...

    def read_ph(self) -> float:
        """Trigger a pH reading and return the result as a float."""
        self._send_command('R')
        return round(float(self._read_response(delay_ms=900)), 3)  # Atlas Scientific claims a +/- 0.001 resolution with the Spear Tip / Soil pH Probe

    def set_temperature_compensation(self, temp: float) -> None:
        """Set the temperature compensation value in degrees C used during pH calculations."""
        self._send_command(f'T,{temp}')
        self._read_response(delay_ms=300)

    def get_temperature_compensation(self) -> float:
        """Return the current temperature compensation value in degrees C."""
        self._send_command('T,?')
        response = self._read_response(delay_ms=300)
        return float(response.split(',')[1])

    def calibrate_mid(self, value: float) -> None:
        """Perform single-point (mid) calibration at the given known pH."""
        self._send_command(f'Cal,mid,{value}')
        self._read_response(delay_ms=900)

    def calibrate_low(self, value: float) -> None:
        """Perform low-point calibration at the given known pH."""
        self._send_command(f'Cal,low,{value}')
        self._read_response(delay_ms=900)

    def calibrate_high(self, value: float) -> None:
        """Perform high-point calibration at the given known pH."""
        self._send_command(f'Cal,high,{value}')
        self._read_response(delay_ms=900)

    def clear_calibration(self) -> None:
        """Erase all stored calibration data from the EZO circuit."""
        self._send_command('Cal,clear')
        self._read_response(delay_ms=900)

    def get_calibration_status(self) -> int:
        """Return number of calibration points set (0, 1, 2, or 3)."""
        self._send_command('Cal,?')
        response = self._read_response(delay_ms=300)
        return int(response.split(',')[1])

    def get_slope(self) -> tuple[float, float]:
        """Return (acid_pct, base_pct) slope percentages from the last calibration."""
        self._send_command('Slope,?')
        response = self._read_response(delay_ms=300)
        parts = response.split(',')
        return float(parts[1]), float(parts[2])

    def get_info(self) -> str:
        """Return the firmware type and version string from the EZO circuit."""
        self._send_command('i')
        return self._read_response(delay_ms=300)

    def get_status(self) -> str:
        """Return the raw status string containing restart reason and supply voltage."""
        self._send_command('Status')
        return self._read_response(delay_ms=300)

    def find(self) -> None:
        """Flash the LED rapidly to help locate the physical EZO circuit."""
        self._send_command('Find')

    def set_led(self, enabled: bool) -> None:
        """Turn the status LED on or off."""
        self._send_command(f'L,{1 if enabled else 0}')
        self._read_response(delay_ms=300)

    def get_led(self) -> bool:
        """Return True if the status LED is currently on."""
        self._send_command('L,?')
        response = self._read_response(delay_ms=300)
        return response.split(',')[1] == '1'

    def set_protocol_lock(self, enabled: bool) -> None:
        """Lock or unlock the EZO circuit's communication protocol."""
        self._send_command(f'Plock,{1 if enabled else 0}')
        self._read_response(delay_ms=300)

    def get_protocol_lock(self) -> bool:
        """Return True if the protocol lock is currently enabled."""
        self._send_command('Plock,?')
        response = self._read_response(delay_ms=300)
        return response.split(',')[1] == '1'

    def sleep(self) -> None:
        """Put the EZO circuit into low-power sleep mode."""
        self._send_command('Sleep')
