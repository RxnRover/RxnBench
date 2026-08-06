"""SiLA2 feature for the Atlas Scientific EZO-PMP dosing pump."""
import asyncio

from unitelabs.cdk import sila

from rxn_bench_dosing_pump.interfaces import (
    DosingPumpProtocol,
    SupportsCalibration,
    SupportsDiagnostics,
    SupportsDirectionInvert,
)
from rxn_bench_dosing_pump.session_log import SessionLog


class DosingPump(sila.Feature):
    """SiLA2 DosingPump feature. Streams dispensing progress and exposes dosing as commands."""

    def __init__(self, pump: DosingPumpProtocol) -> None:
        """
        Args:
            pump: Any object satisfying DosingPumpProtocol (real or mock).
        """
        super().__init__(
            originator="edu.iastate.ames",
            category="rxnbench",
            version="1.0",
            maturity_level="Draft",
        )
        self._pump = pump
        self._log = SessionLog(prefix="dosing_pump")

    # Observable properties

    @sila.ObservableProperty()
    async def volume_dispensed(self) -> sila.Stream[float]:
        """Volume delivered by the current or last dispense, in ml."""
        while True:
            yield await asyncio.to_thread(self._pump.read_volume_dispensed)
            await asyncio.sleep(1.0)

    @sila.ObservableProperty()
    async def dispensing(self) -> sila.Stream[bool]:
        """True while the pump is running."""
        while True:
            yield await asyncio.to_thread(self._pump.is_dispensing)
            await asyncio.sleep(1.0)

    # Unobservable properties

    @sila.UnobservableProperty()
    async def total_volume(self) -> float:
        """Net total volume pumped since the last clear, in ml. Reverse dispensing subtracts."""
        return await asyncio.to_thread(self._pump.total_volume_dispensed)

    @sila.UnobservableProperty()
    async def absolute_total_volume(self) -> float:
        """Total volume pumped since the last clear ignoring direction, in ml."""
        return await asyncio.to_thread(self._pump.absolute_total_volume)

    @sila.UnobservableProperty()
    async def pump_voltage(self) -> float:
        """Motor supply voltage in volts. Requires a pump that reports it."""
        self._require(SupportsDiagnostics, "reading its supply voltage")
        return await asyncio.to_thread(self._pump.pump_voltage)

    @sila.UnobservableProperty()
    async def max_flow_rate(self) -> float:
        """Fastest flow rate in ml/min that SetFlowRate can hold steady.

        Determined after calibration. Not the pump's top speed:
        DispenseContinuously runs the motor open-loop at ~105 ml/min, well
        above this. Exceeding it in SetFlowRate is rejected.
        """
        return await asyncio.to_thread(self._pump.max_flow_rate)

    @sila.UnobservableProperty()
    async def paused(self) -> bool:
        """True while the dispense in progress is paused."""
        return await asyncio.to_thread(self._pump.is_paused)

    @sila.UnobservableProperty()
    async def inverted(self) -> bool:
        """True if the pump's dispensing direction is flipped."""
        self._require(SupportsDirectionInvert, "a persistent direction flip")
        return await asyncio.to_thread(self._pump.is_inverted)

    # Dispensing commands

    @sila.UnobservableCommand()
    async def dispense(self, volume: float) -> None:
        """Dispense a fixed volume and return as soon as the pump has accepted the command.

        Args:
            Volume: Volume to dispense in ml, minimum 0.5. Negative dispenses in
                reverse. Subscribe to Dispensing/VolumeDispensed to follow progress.
        """
        await self._run(self._pump.dispense_volume, volume, log="dispense", volume=volume)

    @sila.UnobservableCommand()
    async def dose_over_time(self, volume: float, minutes: float) -> None:
        """Dispense a fixed volume spread evenly over a set time.

        Args:
            Volume: Volume to dispense in ml, minimum 0.5.
            Minutes: Number of minutes to spread the dispense over. The implied
                rate must not exceed MaxFlowRate.
        """
        await self._run(
            self._pump.dose_over_time, volume, minutes,
            log="dose_over_time", volume=volume, minutes=minutes,
        )

    @sila.UnobservableCommand()
    async def dispense_continuously(self, reverse: bool = False) -> None:
        """Run the pump at its maximum rate until Stop is called.

        Args:
            Reverse: Pump toward the inlet instead of the outlet.
        """
        await self._run(
            self._pump.start_continuous_dispense, reverse,
            log="dispense_continuously", reverse=reverse,
        )

    @sila.UnobservableCommand()
    async def set_flow_rate(self, rate: float, minutes: float = 0.0) -> None:
        """Hold a constant flow rate.

        Args:
            Rate: Flow rate in ml/min, up to MaxFlowRate. Negative runs in reverse.
            Minutes: How long to hold the rate. Zero (the default) runs until
                Stop is called.
        """
        duration = None if minutes <= 0 else minutes
        await self._run(
            self._pump.set_flow_rate, rate, duration,
            log="set_flow_rate", rate=rate, minutes=minutes,
        )

    @sila.UnobservableCommand()
    async def stop(self) -> float:
        """Stop dispensing immediately.

        Returns:
            VolumeDispensed: Volume delivered before stopping, in ml.
        """
        volume = await asyncio.to_thread(self._pump.stop_dispense)
        self._log.log("stop", volume=volume, ok=True)
        return volume

    @sila.UnobservableCommand()
    async def set_paused(self, paused: bool) -> None:
        """Pause or resume the dispense in progress.

        Args:
            Paused: True to pause, False to resume. Idempotent.
        """
        await self._run(self._pump.set_paused, paused, log="set_paused", paused=paused)

    @sila.UnobservableCommand()
    async def set_inverted(self, inverted: bool) -> None:
        """Flip or unflip the pump's dispensing direction. Retained across power loss.

        Args:
            Inverted: True to flip the direction. Idempotent.
        """
        self._require(SupportsDirectionInvert, "a persistent direction flip")
        await self._run(self._pump.set_inverted, inverted, log="set_inverted", inverted=inverted)

    # Volume totals and calibration

    @sila.UnobservableCommand()
    async def clear_total_volume(self) -> None:
        """Reset both total-volume counters to zero."""
        await self._run(self._pump.clear_total_volume, log="clear_total_volume")

    @sila.UnobservableCommand()
    async def calibrate(self, volume: float) -> None:
        """Calibrate the pump against a measured delivered volume.

        Dispense into a graduated container, measure what actually came out, then
        send that value here.

        Args:
            Volume: Volume actually delivered by the last dispense, in ml.
        """
        self._require(SupportsCalibration, "calibration")
        await self._run(self._pump.calibrate, volume, log="calibrate", volume=volume)

    @sila.UnobservableCommand()
    async def clear_calibration(self) -> None:
        """Erase all stored calibration data."""
        self._require(SupportsCalibration, "calibration")
        await self._run(self._pump.clear_calibration, log="clear_calibration")

    @sila.UnobservableCommand()
    async def get_calibration_status(self) -> int:
        """Report whether the pump is calibrated.

        Returns:
            CalibrationStatus: 0 when uncalibrated, non-zero when calibrated.
                Specific non-zero values are pump-defined; the EZO-PMP uses
                1 fixed volume, 2 volume over time, 3 both.
        """
        self._require(SupportsCalibration, "calibration")
        return await asyncio.to_thread(self._pump.calibration_status)

    # Internals

    async def _run(self, fn, *args, log: str, **fields) -> None:
        """Run a blocking pump call off the event loop, logging success or failure."""
        try:
            await asyncio.to_thread(fn, *args)
            self._log.log(log, ok=True, **fields)
        except Exception as exc:
            self._log.log(log, ok=False, error=str(exc), **fields)
            raise

    def _require(self, capability: type, what: str) -> None:
        """Reject a command the attached pump has no hardware support for.

        The feature exposes the full DosingPump surface so one proto, client,
        and widget serve every pump model; a model missing an optional
        capability fails just those calls, with a message naming what is
        missing rather than an AttributeError.
        """
        if not isinstance(self._pump, capability):
            raise NotImplementedError(
                f"This pump does not support {what} "
                f"({type(self._pump).__name__} does not implement {capability.__name__})."
            )
