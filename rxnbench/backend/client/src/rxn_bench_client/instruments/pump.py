"""Peristaltic dosing pump instrument wrapper."""

from __future__ import annotations

import time

from sila2.client import SilaClient

from ._util import _once, _snapshot


class DosingPump:
    """Peristaltic dosing pump. Attach via bench.connect("pump", DosingPump, server=...).

    Dispense commands return as soon as the pump accepts them - the pump keeps
    running in the background. Use :meth:`dispense_and_wait` (or poll
    :meth:`is_dispensing`) when the script must not continue until the liquid
    is actually delivered.

    Examples::

        bench.connect("pump", DosingPump, server="Dosing Pump")

        bench.pump.dispense_and_wait(5.0)        # 5ml, blocks until delivered
        bench.pump.dose_over_time(50.0, 30.0)    # 50ml spread over 30 min
        bench.pump.set_flow_rate(2.0)            # hold 2 ml/min until stopped
        bench.pump.stop()
        bench.log(dispensed=bench.pump.total_volume())
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the dosing pump server.
        """
        self._p = sila

    # Readings

    def volume_dispensed(self) -> float:
        """Volume delivered by the current or last dispense, in ml."""
        return _once(self._p.DosingPump.VolumeDispensed)

    def is_dispensing(self) -> bool:
        """True while the pump is running."""
        return _once(self._p.DosingPump.Dispensing)

    def total_volume(self) -> float:
        """Net total volume pumped since the last clear, in ml. Reverse subtracts."""
        return self._p.DosingPump.TotalVolume.get()

    def absolute_total_volume(self) -> float:
        """Total volume pumped since the last clear ignoring direction, in ml."""
        return self._p.DosingPump.AbsoluteTotalVolume.get()

    def max_flow_rate(self) -> float:
        """Fastest flow rate in ml/min that :meth:`set_flow_rate` can hold steady.

        Determined after calibration. Not the pump's top speed:
        :meth:`dispense_continuously` runs open-loop at ~105 ml/min, well above
        this. Asking :meth:`set_flow_rate` for more is rejected.
        """
        return self._p.DosingPump.MaxFlowRate.get()

    def pump_voltage(self) -> float:
        """Motor supply voltage in volts."""
        return self._p.DosingPump.PumpVoltage.get()

    # Dispensing

    def dispense(self, volume: float) -> None:
        """Dispense a fixed volume in ml (minimum 0.5). Negative dispenses in reverse.

        Returns as soon as the pump accepts the command.
        """
        self._p.DosingPump.Dispense(Volume=volume)

    def dispense_and_wait(self, volume: float, timeout: float = 600.0,
                          poll: float = 0.5) -> float:
        """Dispense a fixed volume and block until the pump reports it finished.

        Args:
            volume: Volume to dispense in ml. Negative dispenses in reverse.
            timeout: Seconds to wait before giving up.
            poll: Seconds between progress checks.

        Returns:
            The volume actually delivered, in ml.

        Raises:
            TimeoutError: The pump was still running when *timeout* elapsed.
        """
        self.dispense(volume)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_dispensing():
                _snapshot(self, "dispense_and_wait")
                return self.volume_dispensed()
            time.sleep(poll)
        raise TimeoutError(
            f"Pump still dispensing after {timeout}s (requested {volume}ml, "
            f"delivered {self.volume_dispensed()}ml so far)"
        )

    def dose_over_time(self, volume: float, minutes: float) -> None:
        """Dispense a volume in ml spread evenly over the given number of minutes."""
        self._p.DosingPump.DoseOverTime(Volume=volume, Minutes=minutes)

    def dispense_continuously(self, reverse: bool = False) -> None:
        """Run at maximum rate until stop() is called."""
        self._p.DosingPump.DispenseContinuously(Reverse=reverse)

    def set_flow_rate(self, rate: float, minutes: float = 0.0) -> None:
        """Hold a constant flow rate in ml/min; zero minutes runs until stop()."""
        self._p.DosingPump.SetFlowRate(Rate=rate, Minutes=minutes)

    def stop(self) -> float:
        """Stop dispensing immediately and return the volume delivered, in ml."""
        return self._p.DosingPump.Stop().VolumeDispensed

    def set_paused(self, paused: bool) -> None:
        """Pause or resume the dispense in progress. Idempotent."""
        self._p.DosingPump.SetPaused(Paused=paused)

    def set_inverted(self, inverted: bool) -> None:
        """Flip or unflip the dispensing direction. Retained across power loss."""
        self._p.DosingPump.SetInverted(Inverted=inverted)

    # Totals and calibration

    def clear_total_volume(self) -> None:
        """Reset both total-volume counters to zero."""
        self._p.DosingPump.ClearTotalVolume()

    def calibrate(self, volume: float) -> None:
        """Calibrate against the volume actually delivered by the last dispense, in ml."""
        self._p.DosingPump.Calibrate(Volume=volume)

    def clear_calibration(self) -> None:
        """Erase all stored calibration data."""
        self._p.DosingPump.ClearCalibration()

    def calibration_status(self) -> int:
        """Return 0 uncalibrated, 1 fixed volume, 2 volume over time, or 3 both."""
        return self._p.DosingPump.GetCalibrationStatus().CalibrationStatus
