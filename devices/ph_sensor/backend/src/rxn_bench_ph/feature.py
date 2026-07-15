"""SiLA2 feature for the Atlas Scientific EZO-pH sensor."""
import asyncio

from unitelabs.cdk import sila

from rxn_bench_ph.interfaces import PHSensorProtocol
from rxn_bench_ph.enums import CalibrationPoint
from rxn_bench_ph.session_log import SessionLog


class PHSensor(sila.Feature):
    """SiLA2 PHSensor feature. Streams pH readings and exposes calibration as commands."""

    def __init__(self, sensor: PHSensorProtocol):
        """
        Args:
            sensor: Any object satisfying PHSensorProtocol (real or mock).
        """
        super().__init__(
            originator="edu.iastate.ames",
            category="rxnbench",
            version="1.0",
            maturity_level="Draft",
        )
        self._sensor = sensor
        self._log = SessionLog(prefix="ph_sensor")

    @sila.ObservableProperty()
    async def ph(self) -> sila.Stream[float]:
        """Current pH of the solution."""
        while True:
            value = self._sensor.read().value
            yield value
            self._log.log("ph", value=value)
            await asyncio.sleep(1.0)

    @sila.UnobservableProperty()
    async def probe_slope(self) -> str:
        """Acid/base slope percentages from the last calibration. Close to 100% = good probe."""
        return str(self._sensor.slope())

    @sila.UnobservableProperty()
    async def temperature(self) -> float:
        """Temperature-compensation value (deg C) currently applied to readings."""
        return self._sensor.get_temperature()

    @sila.UnobservableCommand()
    async def set_temperature(self, temperature: float) -> None:
        """Set the temperature-compensation value used when computing pH.

        Args:
            Temperature: Solution temperature in degrees Celsius. The EZO circuit
                assumes 25 C by default
        """
        self._sensor.set_temperature(temperature)
        self._log.log("set_temperature", temperature=temperature)

    @sila.UnobservableCommand()
    async def calibrate(self, point: CalibrationPoint, value: float) -> None:
        """Calibrate the probe at a known buffer value.

        Args:
            Point: Calibration point - mid, low, high, or clear.
            Value: Known pH of the calibration buffer. Ignored if Point is clear.
        """
        try:
            self._sensor.calibrate(point, value)
            self._log.log("calibrate", point=point.value, buffer_ph=value, ok=True)
        except Exception as exc:
            self._log.log("calibrate", point=point.value, buffer_ph=value, ok=False, error=str(exc))
            raise
