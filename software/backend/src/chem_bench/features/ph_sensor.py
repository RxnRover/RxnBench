"""
SiLA2 feature for the Atlas Scientific EZO-pH sensor.

Exposes pH reading, and calibration as SiLA endpoints.
Hardware communication is handled by AtlasPHSensor - no I2C logic here.
But theoretically could swap out the sensor implementation for a different pH probe without changing the feature code.

Author: John Brittain
Date: Jun 17 2026
"""
import asyncio

from unitelabs.cdk import sila

from chem_bench.io.ph.atlas_ph_sensor import AtlasPHSensor
from chem_bench.io.interfaces.enums import CalibrationPoint


class PHSensor(sila.Feature):

    def __init__(self, sensor: AtlasPHSensor):
        super().__init__(
            originator="edu.iastate.ames",
            category="chembench",
            version="1.0",
            maturity_level="Draft",
        )
        self._sensor = sensor

    @sila.ObservableProperty()
    async def ph(self) -> sila.Stream[float]:
        """Current pH of the solution.

        Returns:
            PH: pH reading.
        """
        while True:
            yield self._sensor.read().value
            await asyncio.sleep(1.0)

    @sila.UnobservableProperty()
    async def probe_slope(self) -> str:
        """Acid/base slope percentages from the last calibration.

        Returns:
            ProbeSlope: Slope string. Close to 100% means good.
        """
        return str(self._sensor.slope())

    @sila.UnobservableCommand()
    async def calibrate(self, point: CalibrationPoint, value: float) -> None:
        """Calibrate the probe at a known buffer value.

        Args:
            Point: Calibration point — mid, low, high, or clear.
            Value: Known pH of the calibration buffer. Ignored if Point is clear.
        """
        self._sensor.calibrate(point, value)
