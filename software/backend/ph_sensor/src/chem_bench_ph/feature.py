"""SiLA2 feature for the Atlas Scientific EZO-pH sensor."""
import asyncio

from unitelabs.cdk import sila

from chem_bench_ph.interfaces import PHSensorProtocol
from chem_bench_ph.enums import CalibrationPoint


class PHSensor(sila.Feature):

    def __init__(self, sensor: PHSensorProtocol):
        super().__init__(
            originator="edu.iastate.ames",
            category="rxnbench",
            version="1.0",
            maturity_level="Draft",
        )
        self._sensor = sensor

    @sila.ObservableProperty()
    async def ph(self) -> sila.Stream[float]:
        """Current pH of the solution."""
        while True:
            yield self._sensor.read().value
            await asyncio.sleep(1.0)

    @sila.UnobservableProperty()
    async def probe_slope(self) -> str:
        """Acid/base slope percentages from the last calibration. Close to 100% = good probe."""
        return str(self._sensor.slope())

    @sila.UnobservableCommand()
    async def calibrate(self, point: CalibrationPoint, value: float) -> None:
        """Calibrate the probe at a known buffer value.

        Args:
            Point: Calibration point - mid, low, high, or clear.
            Value: Known pH of the calibration buffer. Ignored if Point is clear.
        """
        self._sensor.calibrate(point, value)
