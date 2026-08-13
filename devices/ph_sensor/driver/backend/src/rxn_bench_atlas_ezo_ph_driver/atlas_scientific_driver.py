"""Low-level I2C driver for the Atlas Scientific EZO-pH circuit.

The EZO command protocol lives in :class:`~rxn_bench_atlas_ezo_ph_driver.ezo_commands.EZOCommandSet`
(shared with the UART driver); this class supplies the I2C transport (via
:class:`~rxn_bench_atlas_ezo_ph_driver.base_driver.AbstractI2CDriver`) and the I2C-specific
status-byte response parsing.
"""
from rxn_bench_atlas_ezo_ph_driver.base_driver import AbstractI2CDriver
from rxn_bench_atlas_ezo_ph_driver.ezo_commands import EZOCommandSet


DEFAULT_I2C_ADDRESS = 0x63

_STATUS_OK = 1
_STATUS_SYNTAX_ERR = 2
_STATUS_NOT_READY = 254
_STATUS_NO_DATA = 255


class AtlasScientificEZO(AbstractI2CDriver, EZOCommandSet):
    """Low-level EZO-pH command driver over I2C. Speaks the Atlas Scientific I2C protocol."""

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

    def set_i2c_address(self, address: int) -> None:
        """Change the I2C address of the EZO circuit (takes effect after power cycle)."""
        self._send_command(f'I2C,{address}')

    def switch_to_uart(self, baud_rate: int) -> None:
        """Switch the EZO circuit from I2C to UART mode at the given baud rate."""
        self._send_command(f'Baud,{baud_rate}')
