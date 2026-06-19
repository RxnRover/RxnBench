"""
Low-level I2C driver for the Atlas Scientific EZO-pH circuit.

Author: John Brittain
Date: Jun 11 2026
"""
from chem_bench.io.base_driver import AbstractI2CDriver


DEFAULT_I2C_ADDRESS = 0x63  # 99 (0x63) is the default address

_STATUS_OK = 1
_STATUS_SYNTAX_ERR = 2
_STATUS_NOT_READY = 254
_STATUS_NO_DATA = 255


class AtlasScientificEZO(AbstractI2CDriver):
    """Implements the full EZO I2C command list.

    Thin wrapper around the protocol, just sends commands and returns strings.
    pH-specific logic lives in AtlasPHSensor, not here.
    """

    def _parse_response(self, raw: bytes) -> str:
        """Check the status byte and decode the rest as ASCII.

        Parameters
        ----------
        raw : bytes
            Raw bytes from the device.

        Returns
        -------
        str
            Decoded response.

        Raises
        ------
        IOError
            Device not ready, no data, or unknown status code.
        ValueError
            Device says the last command had a syntax error.
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

    # ------------------------------------
    # Reading
    # ------------------------------------

    def read_ph(self) -> float:
        """Grab a single pH reading.

        Returns
        -------
        float
            pH value from the circuit.
        """
        self._send_command('R')
        return float(self._read_response(delay_ms=900))

    # ------------------------------------
    # Temperature compensation
    # ------------------------------------

    def set_temperature_compensation(self, temp: float) -> None:
        """Set the temperature the circuit uses to compensate pH.

        Parameters
        ----------
        temp : float
            Temperature in °C.
        """
        self._send_command(f'T,{temp}')
        self._read_response(delay_ms=300)

    def get_temperature_compensation(self) -> float:
        """Check what temperature is currently set for compensation.

        Returns
        -------
        float
            Temperature in °C.
        """
        self._send_command('T,?')
        response = self._read_response(delay_ms=300)
        return float(response.split(',')[1])

    # ------------------------------------
    # Calibration
    # ------------------------------------

    def calibrate_mid(self, value: float) -> None:
        """Calibrate at the midpoint buffer (usually pH 7.0).

        Parameters
        ----------
        value : float
            Known pH of the buffer.
        """
        self._send_command(f'Cal,mid,{value}')
        self._read_response(delay_ms=900)

    def calibrate_low(self, value: float) -> None:
        """Calibrate at the low-point buffer (usually pH 4.0).

        Parameters
        ----------
        value : float
            Known pH of the buffer.
        """
        self._send_command(f'Cal,low,{value}')
        self._read_response(delay_ms=900)

    def calibrate_high(self, value: float) -> None:
        """Calibrate at the high-point buffer (usually pH 10.0).

        Parameters
        ----------
        value : float
            Known pH of the buffer.
        """
        self._send_command(f'Cal,high,{value}')
        self._read_response(delay_ms=900)

    def clear_calibration(self) -> None:
        """Wipe all stored calibration data."""
        self._send_command('Cal,clear')
        self._read_response(delay_ms=900)

    def get_calibration_status(self) -> int:
        """Check how many calibration points are stored.

        Returns
        -------
        int
            0, 1, 2, or 3 points.
        """
        self._send_command('Cal,?')
        response = self._read_response(delay_ms=300)
        return int(response.split(',')[1])

    # ------------------------------------
    # Probe diagnostics
    # ------------------------------------

    def get_slope(self) -> tuple[float, float]:
        """Get the probe's acid and base slope, useful for checking probe health.

        Returns
        -------
        tuple[float, float]
            (acid_slope_pct, base_slope_pct). Close to 100% means the probe is good.
        """
        self._send_command('Slope,?')
        response = self._read_response(delay_ms=300)
        parts = response.split(',')
        return float(parts[1]), float(parts[2])

    # ------------------------------------
    # Device info and status
    # ------------------------------------

    def get_info(self) -> str:
        """Get device type and firmware version.

        Returns
        -------
        str
            Raw string from the circuit, e.g. '?I,pH,2.12'.
        """
        self._send_command('i')
        return self._read_response(delay_ms=300)

    def get_status(self) -> str:
        """Get circuit status: restart reason and supply voltage.

        Returns
        -------
        str
            Raw string from the circuit, e.g. '?Status,P,5.038'.
        """
        self._send_command('Status')
        return self._read_response(delay_ms=300)

    # ------------------------------------
    # Device management
    # ------------------------------------

    def find(self) -> None:
        """Flash the LED white so you can find which device this is on the bus.

        Send any command after to stop the blinking.
        """
        self._send_command('Find')

    def set_led(self, enabled: bool) -> None:
        """Turn the status LED on or off.

        Parameters
        ----------
        enabled : bool
        """
        self._send_command(f'L,{1 if enabled else 0}')
        self._read_response(delay_ms=300)

    def get_led(self) -> bool:
        """Check if the status LED is on.

        Returns
        -------
        bool
        """
        self._send_command('L,?')
        response = self._read_response(delay_ms=300)
        return response.split(',')[1] == '1'

    def set_protocol_lock(self, enabled: bool) -> None:
        """Lock the device to I2C so it can't accidentally switch to UART.

        Parameters
        ----------
        enabled : bool
        """
        self._send_command(f'Plock,{1 if enabled else 0}')
        self._read_response(delay_ms=300)

    def get_protocol_lock(self) -> bool:
        """Check whether protocol lock is on.

        Returns
        -------
        bool
        """
        self._send_command('Plock,?')
        response = self._read_response(delay_ms=300)
        return response.split(',')[1] == '1'

    def set_i2c_address(self, address: int) -> None:
        """Change the device's I2C address. It resets immediately after - update your code too.

        Parameters
        ----------
        address : int
            New address (1–127).
        """
        self._send_command(f'I2C,{address}')

    def sleep(self) -> None:
        """Put the device into low-power sleep. Send any command to wake it back up."""
        self._send_command('Sleep')

    def switch_to_uart(self, baud_rate: int) -> None:
        """Switch from I2C to UART mode. The device won't respond to I2C after this.

        Parameters
        ----------
        baud_rate : int
            Target baud rate (e.g. 9600, 115200).
        """
        self._send_command(f'Baud,{baud_rate}')
