"""Low-level I2C driver for the Atlas Scientific EZO-pH circuit."""
from chem_bench_ph.base_driver import AbstractI2CDriver


DEFAULT_I2C_ADDRESS = 0x63

_STATUS_OK = 1
_STATUS_SYNTAX_ERR = 2
_STATUS_NOT_READY = 254
_STATUS_NO_DATA = 255


class AtlasScientificEZO(AbstractI2CDriver):

    def _parse_response(self, raw: bytes) -> str:
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
        self._send_command('R')
        return float(self._read_response(delay_ms=900))

    def set_temperature_compensation(self, temp: float) -> None:
        self._send_command(f'T,{temp}')
        self._read_response(delay_ms=300)

    def get_temperature_compensation(self) -> float:
        self._send_command('T,?')
        response = self._read_response(delay_ms=300)
        return float(response.split(',')[1])

    def calibrate_mid(self, value: float) -> None:
        self._send_command(f'Cal,mid,{value}')
        self._read_response(delay_ms=900)

    def calibrate_low(self, value: float) -> None:
        self._send_command(f'Cal,low,{value}')
        self._read_response(delay_ms=900)

    def calibrate_high(self, value: float) -> None:
        self._send_command(f'Cal,high,{value}')
        self._read_response(delay_ms=900)

    def clear_calibration(self) -> None:
        self._send_command('Cal,clear')
        self._read_response(delay_ms=900)

    def get_calibration_status(self) -> int:
        self._send_command('Cal,?')
        response = self._read_response(delay_ms=300)
        return int(response.split(',')[1])

    def get_slope(self) -> tuple[float, float]:
        self._send_command('Slope,?')
        response = self._read_response(delay_ms=300)
        parts = response.split(',')
        return float(parts[1]), float(parts[2])

    def get_info(self) -> str:
        self._send_command('i')
        return self._read_response(delay_ms=300)

    def get_status(self) -> str:
        self._send_command('Status')
        return self._read_response(delay_ms=300)

    def find(self) -> None:
        self._send_command('Find')

    def set_led(self, enabled: bool) -> None:
        self._send_command(f'L,{1 if enabled else 0}')
        self._read_response(delay_ms=300)

    def get_led(self) -> bool:
        self._send_command('L,?')
        response = self._read_response(delay_ms=300)
        return response.split(',')[1] == '1'

    def set_protocol_lock(self, enabled: bool) -> None:
        self._send_command(f'Plock,{1 if enabled else 0}')
        self._read_response(delay_ms=300)

    def get_protocol_lock(self) -> bool:
        self._send_command('Plock,?')
        response = self._read_response(delay_ms=300)
        return response.split(',')[1] == '1'

    def set_i2c_address(self, address: int) -> None:
        self._send_command(f'I2C,{address}')

    def sleep(self) -> None:
        self._send_command('Sleep')

    def switch_to_uart(self, baud_rate: int) -> None:
        self._send_command(f'Baud,{baud_rate}')
