"""Atlas Scientific EZO-pH sensor, implements BaseSensor / PHSensorProtocol."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from rxn_bench_ph.base_sensor import BaseSensor, SensorReading
from rxn_bench_ph.atlas_scientific_driver import AtlasScientificEZO, DEFAULT_I2C_ADDRESS


@dataclass
class PHReading(SensorReading):
    """A single pH measurement with metadata."""

    value: float = 0.0
    unit: str = 'pH'
    sensor_id: str = ''
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AtlasPHSensor(BaseSensor):
    """Atlas Scientific EZO-pH sensor, over I2C or UART."""

    display_name = 'Atlas Scientific pH Sensor'
    description = 'Measures solution pH via an Atlas Scientific EZO-pH circuit.'

    def __init__(
        self,
        i2c_bus=None,
        sensor_id: str = 'atlas_ph',
        address: int = DEFAULT_I2C_ADDRESS,
        *,
        driver=None,
    ):
        """
        Args:
            i2c_bus:   Open SMBus (or compatible) object for the I2C bus. Used to
                       build the default I2C driver when *driver* is not given.
            sensor_id: Logical identifier used in readings and logs.
            address:   7-bit I2C address of the EZO-pH circuit (I2C path only).
            driver:    A ready EZO command driver (e.g. ``AtlasScientificEZOUart``)
                       to use instead of building an I2C one - the transport-agnostic
                       injection point for the UART path. Mutually exclusive with
                       *i2c_bus*.

        Raises:
            ValueError: If neither *i2c_bus* nor *driver* is provided.
        """
        super().__init__(sensor_id)
        if driver is not None:
            self._driver = driver
        elif i2c_bus is not None:
            self._driver = AtlasScientificEZO(i2c_bus, address)
        else:
            raise ValueError("AtlasPHSensor requires either an i2c_bus or a driver")

    def read(self) -> PHReading:
        value = self._driver.read_ph()
        return PHReading(value=value, sensor_id=self.sensor_id)

    def calibrate(self, point: str, value: float) -> None:
        """Calibrate the probe at a known pH buffer.

        Args:
            point: Calibration point - ``'mid'``, ``'low'``, ``'high'``, or ``'clear'``.
            value: Known pH of the calibration buffer. Ignored when *point* is ``'clear'``.

        Raises:
            ValueError: If *point* is not one of the accepted strings.
        """
        if point == 'mid':
            self._driver.calibrate_mid(value)
        elif point == 'low':
            self._driver.calibrate_low(value)
        elif point == 'high':
            self._driver.calibrate_high(value)
        elif point == 'clear':
            self._driver.clear_calibration()
        else:
            raise ValueError(f"Unknown calibration point {point!r}. Use 'mid', 'low', 'high', or 'clear'.")

    def status(self) -> dict:
        """Return hardware restart reason and supply voltage from the sensor."""
        raw = self._driver.get_status()
        parts = raw.lstrip('?').split(',')
        return {
            'restart_reason': parts[1] if len(parts) > 1 else None,
            'voltage': float(parts[2]) if len(parts) > 2 else None,
        }

    def set_temperature(self, temp: float) -> None:
        """Set the temperature compensation value used for pH calculations."""
        self._driver.set_temperature_compensation(temp)

    def get_temperature(self) -> float:
        """Return the current temperature compensation value in °C."""
        return self._driver.get_temperature_compensation()

    def slope(self) -> tuple[float, float]:
        """Return (acid_pct, base_pct) slope percentages from the last calibration."""
        return self._driver.get_slope()

    def calibration_status(self) -> int:
        """Return number of calibration points set (0, 1, 2, or 3)."""
        return self._driver.get_calibration_status()

    def info(self) -> str:
        """Return firmware type and version string from the EZO circuit."""
        return self._driver.get_info()

    def find(self) -> None:
        """Flash the LED to help locate the physical device on the I2C bus."""
        self._driver.find()

    def sleep(self) -> None:
        """Put the EZO circuit into low-power sleep mode."""
        self._driver.sleep()

    def set_led(self, enabled: bool) -> None:
        """Turn the status LED on or off."""
        self._driver.set_led(enabled)

    def get_led(self) -> bool:
        """Return True if the status LED is currently on."""
        return self._driver.get_led()
