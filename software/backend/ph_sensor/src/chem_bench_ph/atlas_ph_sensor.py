"""Atlas Scientific EZO-pH sensor, implements BaseSensor / PHSensorProtocol."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from chem_bench_ph.base_sensor import BaseSensor, SensorReading
from chem_bench_ph.atlas_scientific_driver import AtlasScientificEZO, DEFAULT_I2C_ADDRESS


@dataclass
class PHReading(SensorReading):
    value: float = 0.0
    unit: str = 'pH'
    sensor_id: str = ''
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AtlasPHSensor(BaseSensor):
    """Atlas Scientific EZO-pH sensor."""

    display_name = 'Atlas Scientific pH Sensor'
    description = 'Measures solution pH via Atlas Scientific EZO-pH circuit over I2C.'

    def __init__(self, i2c_bus, sensor_id: str = 'atlas_ph', address: int = DEFAULT_I2C_ADDRESS):
        super().__init__(sensor_id)
        self._driver = AtlasScientificEZO(i2c_bus, address)

    def read(self) -> PHReading:
        value = self._driver.read_ph()
        return PHReading(value=value, sensor_id=self.sensor_id)

    def calibrate(self, point: str, value: float) -> None:
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
        raw = self._driver.get_status()
        parts = raw.lstrip('?').split(',')
        return {
            'restart_reason': parts[1] if len(parts) > 1 else None,
            'voltage': float(parts[2]) if len(parts) > 2 else None,
        }

    def set_temperature(self, temp: float) -> None:
        self._driver.set_temperature_compensation(temp)

    def get_temperature(self) -> float:
        return self._driver.get_temperature_compensation()

    def slope(self) -> tuple[float, float]:
        return self._driver.get_slope()

    def calibration_status(self) -> int:
        return self._driver.get_calibration_status()

    def info(self) -> str:
        return self._driver.get_info()

    def find(self) -> None:
        self._driver.find()

    def sleep(self) -> None:
        self._driver.sleep()

    def set_led(self, enabled: bool) -> None:
        self._driver.set_led(enabled)

    def get_led(self) -> bool:
        return self._driver.get_led()
