"""
Atlas Scientific EZO-pH sensor, implements BaseSensor.

Satisfies: PHSensorProtocol (io/interfaces/ph_sensor.py)

Author: John Brittain
Date: Jun 11 2026
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from chem_bench.io.base_sensor import BaseSensor, SensorReading
from chem_bench.io.ph.atlas_scientific_driver import AtlasScientificEZO, DEFAULT_I2C_ADDRESS


@dataclass
class PHReading(SensorReading):
    """A single pH measurement with timestamp and metadata.

    Attributes
    ----------
    value : float
        pH value (0–14).
    unit : str
        Always 'pH'.
    sensor_id : str
        Which sensor produced this.
    timestamp : datetime
        UTC time the reading was taken.
    """
    value: float = 0.0
    unit: str = 'pH'
    sensor_id: str = ''
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AtlasPHSensor(BaseSensor):
    """Atlas Scientific EZO-pH sensor.

    Wraps AtlasScientificEZO and implements the BaseSensor interface.
    This is what the rest of the system talks to, not the driver directly.

    Parameters
    ----------
    i2c_bus :
        Bus object with ``read(address, n_bytes)`` and ``write(address, data)``.
    sensor_id : str, optional
        Unique ID for this sensor instance.
    address : int, optional
        I2C address. Defaults to 0x63.
    """

    display_name = 'Atlas Scientific pH Sensor'
    description = 'Measures solution pH via Atlas Scientific EZO-pH circuit over I2C.'

    def __init__(self, i2c_bus, sensor_id: str = 'atlas_ph', address: int = DEFAULT_I2C_ADDRESS):
        super().__init__(sensor_id)
        self._driver = AtlasScientificEZO(i2c_bus, address)

    # ------------------------------------
    # BaseSensor interface
    # ------------------------------------

    def read(self) -> PHReading:
        """Take a single pH reading.

        Returns
        -------
        PHReading
            Timestamped measurement.

        Raises
        ------
        IOError
            If the sensor isn't ready or returns no data.
        """
        value = self._driver.read_ph()
        return PHReading(value=value, sensor_id=self.sensor_id)

    # ------------------------------------
    # pH-specific
    # ------------------------------------

    def calibrate(self, point: str, value: float) -> None:
        """Calibrate at a known buffer value.

        Parameters
        ----------
        point : {'mid', 'low', 'high', 'clear'}
            Which calibration point to set. Use 'clear' to wipe stored calibration.
        value : float
            Known pH of the buffer. Ignored if point is 'clear'.

        Raises
        ------
        ValueError
            If point isn't one of the expected values.
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
        """Get restart reason and supply voltage from the circuit.

        Returns
        -------
        dict
            Keys: ``restart_reason`` (str), ``voltage`` (float).
        """
        raw = self._driver.get_status()
        parts = raw.lstrip('?').split(',')
        return {
            'restart_reason': parts[1] if len(parts) > 1 else None,
            'voltage': float(parts[2]) if len(parts) > 2 else None,
        }

    def set_temperature(self, temp: float) -> None:
        """Set temperature compensation. Call this if the solution temperature changes.

        Parameters
        ----------
        temp : float
            Temperature in °C.
        """
        self._driver.set_temperature_compensation(temp)

    def get_temperature(self) -> float:
        """Check what temperature is set for compensation.

        Returns
        -------
        float
            Temperature in °C.
        """
        return self._driver.get_temperature_compensation()

    def slope(self) -> tuple[float, float]:
        """Get probe slope to check if the probe is still good.

        Returns
        -------
        tuple[float, float]
            (acid_slope_pct, base_slope_pct).
        """
        return self._driver.get_slope()

    def calibration_status(self) -> int:
        """Check how many calibration points are stored.

        Returns
        -------
        int
            0, 1, 2, or 3.
        """
        return self._driver.get_calibration_status()

    def info(self) -> str:
        """Get device type and firmware version string.

        Returns
        -------
        str
            e.g. '?I,pH,2.12'.
        """
        return self._driver.get_info()

    # ------------------------------------
    # Device management
    # ------------------------------------

    def find(self) -> None:
        """Flash the LED white to find this device on the bus."""
        self._driver.find()

    def sleep(self) -> None:
        """Put the device to sleep. Send any command to wake it."""
        self._driver.sleep()

    def set_led(self, enabled: bool) -> None:
        """Turn the status LED on or off.

        Parameters
        ----------
        enabled : bool
        """
        self._driver.set_led(enabled)

    def get_led(self) -> bool:
        """Check if the status LED is on.

        Returns
        -------
        bool
        """
        return self._driver.get_led()
