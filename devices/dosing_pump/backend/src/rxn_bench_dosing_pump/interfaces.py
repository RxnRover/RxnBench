"""Interface contract for dosing pumps.

Split into a small core every dosing pump can satisfy, plus opt-in capability
protocols for features that are not universal. A pump only has to implement
:class:`DosingPumpProtocol`; the SiLA feature checks the optional protocols at
runtime (they are ``runtime_checkable``) and rejects the corresponding commands
with a clear message on hardware that lacks them.

The point is reuse: the feature, proto, client, and Qt widget depend on this
contract, not on any vendor. A second pump model implementing the core reuses
all of them without a line of new frontend code - see the SiLA-feature reuse
note in ``devices/dosing_pump/README.md``.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DosingPumpProtocol(Protocol):
    """Core contract required by the DosingPump SiLA feature.

    Volumes are millilitres and flow rates millilitres per minute throughout.
    A negative volume or rate means reverse (pump toward the inlet).

    Deliberately minimal: only operations any dosing pump can be expected to
    support. Anything vendor-specific belongs in a capability protocol below.
    """

    def read_volume_dispensed(self) -> float:
        """Return the volume dispensed so far by the current or last dispense, in ml."""
        ...

    def dispense_volume(self, volume: float) -> None:
        """Dispense a fixed volume in ml. Negative dispenses in reverse.

        Implementations reject volumes below whatever minimum the hardware has.
        """
        ...

    def dose_over_time(self, volume: float, minutes: float) -> None:
        """Dispense a fixed volume in ml spread evenly over the given number of minutes."""
        ...

    def start_continuous_dispense(self, reverse: bool = False) -> None:
        """Run the pump at its top speed until stopped. The rate is not selectable."""
        ...

    def set_flow_rate(self, rate: float, minutes: float | None = None) -> None:
        """Hold a constant flow rate in ml/min.

        Args:
            rate: Target flow rate in ml/min, up to :meth:`max_flow_rate`.
                Negative runs in reverse.
            minutes: How long to hold the rate; None runs until stopped.
        """
        ...

    def max_flow_rate(self) -> float:
        """Return the fastest flow rate in ml/min that :meth:`set_flow_rate` can hold.

        Typically below the pump's top speed, since holding a metered rate needs
        a controlled regime that open-loop continuous dispensing does not.
        """
        ...

    def set_paused(self, paused: bool) -> None:
        """Pause or resume the dispense in progress. Idempotent."""
        ...

    def is_paused(self) -> bool:
        """Return True while the dispense in progress is paused."""
        ...

    def stop_dispense(self) -> float:
        """Stop dispensing immediately and return the volume dispensed, in ml."""
        ...

    def is_dispensing(self) -> bool:
        """Return True while the pump is running."""
        ...

    def total_volume_dispensed(self) -> float:
        """Return the net total volume pumped since the last clear, in ml.

        Reverse dispensing subtracts from this, so it can be negative.
        """
        ...

    def absolute_total_volume(self) -> float:
        """Return the total volume pumped since the last clear ignoring direction, in ml.

        A pump keeping only one counter may return ``abs(total_volume_dispensed())``,
        which differs after any reverse dispensing but is the closest available.
        """
        ...

    def clear_total_volume(self) -> None:
        """Reset the total-volume counters to zero."""
        ...


@runtime_checkable
class SupportsCalibration(Protocol):
    """Pumps that can be calibrated against a measured delivered volume."""

    def calibrate(self, volume: float) -> None:
        """Calibrate against the volume actually delivered, in ml, by the last dispense."""
        ...

    def clear_calibration(self) -> None:
        """Erase all stored calibration data."""
        ...

    def calibration_status(self) -> int:
        """Return 0 when uncalibrated, non-zero when calibrated.

        The meaning of specific non-zero values is pump-defined (the EZO-PMP
        uses 1 = fixed volume, 2 = volume over time, 3 = both).
        """
        ...


@runtime_checkable
class SupportsDirectionInvert(Protocol):
    """Pumps with a persistent direction flip, separate from per-command sign."""

    def set_inverted(self, inverted: bool) -> None:
        """Set whether the pump's dispensing direction is flipped. Idempotent."""
        ...

    def is_inverted(self) -> bool:
        """Return True if the dispensing direction is flipped."""
        ...


@runtime_checkable
class SupportsDiagnostics(Protocol):
    """Pumps that report their own electrical health."""

    def pump_voltage(self) -> float:
        """Return the motor supply voltage in volts."""
        ...
