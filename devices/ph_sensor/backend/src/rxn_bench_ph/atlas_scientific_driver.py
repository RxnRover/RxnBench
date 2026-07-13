"""Low-level I2C driver for the Atlas Scientific EZO-pH circuit."""
from rxn_bench_ph.base_driver import AbstractI2CDriver


DEFAULT_I2C_ADDRESS = 0x63

_STATUS_OK = 1
_STATUS_SYNTAX_ERR = 2
_STATUS_NOT_READY = 254
_STATUS_NO_DATA = 255


class AtlasScientificEZO(AbstractI2CDriver):
    """Low-level EZO-pH command driver. Wraps the Atlas Scientific I2C command protocol."""

    def _parse_response(self, raw: bytes) -> str:
        """Decode a raw I2C response, checking the status byte.

        Raises:
            IOError:    Response is empty, sensor not ready, or no data available.
            ValueError: Sensor reported a syntax error in the last command sent.
        """
        if not raw:
            raise IOError("Empty response from sensor")
        code = raw[0]
        if code == _STATUS_NOT_READY:
            raise IOError("Sensor not ready")
        if code == _STATUS_SYNTAX_ERR:
            raise ValueError("Syntax error in command sent to sensor")
        if code == _STATUS_NO_DATA:
            raise IOError("No data available")
        if code != _STATUS_OK:
            raise IOError(f"Unexpected response code: {code}")
        return raw[1:].rstrip(b'\x00').decode('ascii').strip()

    def read_ph(self) -> float:
        """Trigger a pH reading and return the result as a float."""
        self._send_command('R')
        return round(float(self._read_response(delay_ms=900)), 3)  # Atlas Scientific claims a +/- 0.001 resolution with the Spear Tip / Soil pH Probe 

    def set_temperature_compensation(self, temp: float) -> None:
        """Set the temperature compensation value in °C used during pH calculations."""
        self._send_command(f'T,{temp}')
        self._read_response(delay_ms=300)

    def get_temperature_compensation(self) -> float:
        """Return the current temperature compensation value in °C."""
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

    def set_i2c_address(self, address: int) -> None:
        """Change the I2C address of the EZO circuit (takes effect after power cycle)."""
        self._send_command(f'I2C,{address}')

    def sleep(self) -> None:
        """Put the EZO circuit into low-power sleep mode."""
        self._send_command('Sleep')

    def switch_to_uart(self, baud_rate: int) -> None:
        """Switch the EZO circuit from I2C to UART mode at the given baud rate."""
        self._send_command(f'Baud,{baud_rate}')
