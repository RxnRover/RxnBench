"""Atlas Scientific EZO-PMP dosing pump, implements DosingPumpProtocol.

Thin adapter over the raw command set: it turns the pump's two *toggle*
commands (``P`` pause, ``Invert``) into idempotent setters by reading the
current state first, so scripts can assert a desired state rather than track
parity. Everything else forwards straight through.
"""
from __future__ import annotations


class AtlasDosingPump:
    """Atlas Scientific EZO-PMP peristaltic dosing pump."""

    display_name = "Atlas Scientific EZO-PMP"
    description = "Atlas Scientific EZO-PMP Dosing Pump."

    def __init__(self, driver) -> None:
        """
        Args:
            driver: A ready EZO-PMP command driver, e.g.
                :class:`~rxn_bench_dosing_pump.atlas_scientific_uart_driver.AtlasScientificEZOPumpUart`.
        """
        self._driver = driver

    # Dispensing

    def read_volume_dispensed(self) -> float:
        """Return the volume dispensed by the current or last dispense, in ml."""
        return self._driver.read_volume_dispensed()

    def dispense_volume(self, volume: float) -> None:
        """Dispense a fixed volume in ml. Negative dispenses in reverse."""
        self._driver.dispense_volume(volume)

    def dose_over_time(self, volume: float, minutes: float) -> None:
        """Dispense a volume in ml spread evenly over the given number of minutes."""
        self._driver.dose_over_time(volume, minutes)

    def start_continuous_dispense(self, reverse: bool = False) -> None:
        """Run the pump at its maximum rate until stopped."""
        self._driver.dispense_continuously(reverse)

    def set_flow_rate(self, rate: float, minutes: float | None = None) -> None:
        """Hold a constant flow rate in ml/min; None minutes runs until stopped."""
        self._driver.set_constant_flow_rate(rate, minutes)

    def stop_dispense(self) -> float:
        """Stop dispensing and return the volume dispensed, in ml."""
        return self._driver.stop()

    def is_dispensing(self) -> bool:
        """Return True while the pump is running."""
        _, running = self._driver.get_dispense_status()
        return running

    # Toggle commands exposed as idempotent setters

    def set_paused(self, paused: bool) -> None:
        """Pause or resume the dispense in progress.

        ``P`` is a toggle on the hardware, so the current state is read first
        and the command sent only when it would actually change something.
        """
        if self._driver.get_pause_status() != paused:
            self._driver.pause()

    def is_paused(self) -> bool:
        """Return True while the dispense in progress is paused."""
        return self._driver.get_pause_status()

    def set_inverted(self, inverted: bool) -> None:
        """Set whether the dispensing direction is flipped.

        ``Invert`` is a toggle on the hardware, and the setting survives power
        loss, so the current state is read first to keep this idempotent.
        """
        if self._driver.get_invert_status() != inverted:
            self._driver.invert()

    def is_inverted(self) -> bool:
        """Return True if the dispensing direction is flipped."""
        return self._driver.get_invert_status()

    # Volume totals

    def total_volume_dispensed(self) -> float:
        """Return the net total volume pumped since the last clear, in ml."""
        return self._driver.get_total_volume()

    def absolute_total_volume(self) -> float:
        """Return the total volume pumped since the last clear ignoring direction, in ml."""
        return self._driver.get_absolute_total_volume()

    def clear_total_volume(self) -> None:
        """Reset both total-volume counters to zero."""
        self._driver.clear_total_volume()

    # Calibration and diagnostics

    def pump_voltage(self) -> float:
        """Return the motor supply voltage in volts."""
        return self._driver.get_pump_voltage()

    def max_flow_rate(self) -> float:
        """Return the maximum *metered* flow rate in ml/min (constant-rate mode).

        Not the pump's top speed; continuous dispensing runs faster, open-loop.
        """
        return self._driver.get_max_flow_rate()

    def calibrate(self, volume: float) -> None:
        """Calibrate against the volume actually delivered by the last dispense, in ml."""
        self._driver.calibrate(volume)

    def clear_calibration(self) -> None:
        """Erase all stored calibration data."""
        self._driver.clear_calibration()

    def calibration_status(self) -> int:
        """Return 0 uncalibrated, 1 fixed volume, 2 volume over time, or 3 both."""
        return self._driver.get_calibration_status()

    def status(self) -> dict:
        """Return the pump's restart reason and Vcc voltage."""
        parts = self._driver.get_status().lstrip("?").split(",")
        return {
            "restart_reason": parts[1] if len(parts) > 1 else None,
            "voltage": float(parts[2]) if len(parts) > 2 else None,
        }

    def info(self) -> str:
        """Return the device type and firmware version string."""
        return self._driver.get_info()

    # Circuit housekeeping
    #
    # Not on the SiLA feature (matching rxn_bench_ph, where these are
    # driver-level only): they identify or power-manage the circuit rather than
    # dose liquid, so they belong to whoever is holding the hardware.

    def find(self) -> None:
        """Blink the LED rapidly to locate this circuit among others on the bench."""
        self._driver.find()

    def set_led(self, enabled: bool) -> None:
        """Turn the status LED on or off."""
        self._driver.set_led(enabled)

    def get_led(self) -> bool:
        """Return True if the status LED is currently on."""
        return self._driver.get_led()

    def sleep(self) -> None:
        """Put the circuit into low-power sleep. Call :meth:`wake` before using it again.

        Affects the control system only - the 12-24V motor supply is untouched.
        """
        self._driver.sleep()

    def wake(self) -> None:
        """Wake the circuit from sleep mode."""
        self._driver.wake()
