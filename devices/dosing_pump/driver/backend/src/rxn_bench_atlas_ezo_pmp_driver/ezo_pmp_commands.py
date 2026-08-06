"""Atlas Scientific EZO-PMP command set.

The EZO command protocol (``D,15``, ``DC,25,40``, ``TV,?``, ...) is identical
whether the circuit is spoken to over UART or I2C - only the byte-level
send/receive differs, so it lives here and each transport supplies only
:meth:`_send_command` / :meth:`_read_response`.

Deliberately a separate copy of the analogous layer in ``rxn_bench_ph``: the
two devices share a *vendor protocol family*, not a command set (dispensing vs
potentiometry), and per CURRENT_STATE.md §8 device backends stay independently
deployable rather than taking a runtime dependency on each other.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod

# Every EZO-PMP command uses the same 300ms processing delay (datasheet pg.
# 51-74), unlike the EZO-pH where reads need 900ms.
DELAY_MS = 300

# Smallest volume the pump can dispense; below this it replies *MINVOL.
MIN_DISPENSE_ML = 0.5


def _fmt(value: float) -> str:
    """Format a number for the wire without trailing zeros (15.0 -> '15')."""
    return f"{value:g}"


class EZOPumpCommandSet(ABC):
    """The EZO-PMP command protocol, independent of the underlying transport."""

    def __init__(self) -> None:
        # Guards each command's send+read exchange. The SiLA server polls two
        # observable properties (VolumeDispensed, Dispensing) concurrently at
        # 1Hz, each off-loaded to its own thread via asyncio.to_thread, plus
        # whatever command a script has in flight (Dispense, Stop, ...) - all
        # sharing this one port. Without serializing the full exchange, two
        # threads' writes/reads interleave on the wire: reproduced against
        # real EZO-PMP hardware 2026-08-04 as garbled reads ('D,100,', 'O',
        # 'OK?-.0,0*', ...) whenever a poll raced a Dispense call.
        self._lock = threading.Lock()

    @abstractmethod
    def _send_command(self, cmd: str) -> None:
        """Write an ASCII command string to the device (e.g. 'D,15', 'TV,?')."""
        ...

    @abstractmethod
    def _read_response(self, delay_ms: int = DELAY_MS, done_terminates: bool = False) -> str:
        """Return the device's decoded ASCII reply, or '' for an ack-only command.

        Args:
            delay_ms: The command's processing delay, which sizes the read timeout.
            done_terminates: True only for ``X``, whose reply *is* a ``*DONE``
                line. Otherwise a ``*DONE`` may arrive unsolicited at any moment
                (a dispense finishing on its own) and must never be mistaken for
                the reply to the command in flight.
        """
        ...

    def _transact(self, cmd: str, delay_ms: int = DELAY_MS, done_terminates: bool = False) -> str:
        """Send *cmd* and read its reply as one atomic exchange (see :attr:`_lock`)."""
        with self._lock:
            self._send_command(cmd)
            return self._read_response(delay_ms, done_terminates)

    @staticmethod
    def _field(response: str, index: int) -> str:
        """Return one comma-separated field of a ``?Cmd,a,b`` style reply.

        Raises:
            ValueError: The reply had fewer fields than expected.
        """
        parts = response.split(",")
        if len(parts) <= index:
            raise ValueError(f"Malformed pump response {response!r}: expected >{index} fields")
        return parts[index].strip()

    # Dispensing

    def dispense_volume(self, volume: float) -> None:
        """Dispense a fixed volume in ml (``D,[ml]``). Negative dispenses in reverse."""
        self._transact(f"D,{_fmt(volume)}")

    def dispense_continuously(self, reverse: bool = False) -> None:
        """Run at maximum rate until stopped (``D,*`` / ``D,-*``)."""
        self._transact("D,-*" if reverse else "D,*")

    def dose_over_time(self, volume: float, minutes: float) -> None:
        """Dispense a volume in ml spread over a number of minutes (``D,[ml],[min]``)."""
        self._transact(f"D,{_fmt(volume)},{_fmt(minutes)}")

    def set_constant_flow_rate(self, rate: float, minutes: float | None = None) -> None:
        """Hold a constant flow rate in ml/min (``DC,[ml/min],[min|*]``).

        Args:
            rate: Flow rate in ml/min; negative runs in reverse.
            minutes: Duration to hold the rate, or None to run indefinitely.
        """
        duration = "*" if minutes is None else _fmt(minutes)
        self._transact(f"DC,{_fmt(rate)},{duration}")

    def get_max_flow_rate(self) -> float:
        """Return the maximum *metered* flow rate in ml/min (``DC,?`` -> ``?MAXRATE,58.5``).

        This is the fastest rate the pump can hold steady in constant-flow-rate
        mode, and is determined after calibration. It is **not** the pump's top
        speed: continuous dispensing (``D,*``) runs the motor open-loop at
        ~105 ml/min, well above this. Requesting more than this in ``DC`` gets
        ``*TOOFAST``.
        """
        return float(self._field(self._transact("DC,?"), 1))

    def get_dispense_status(self) -> tuple[float, bool]:
        """Return (last volume requested/dispensed in ml, pump running) (``D,?``)."""
        response = self._transact("D,?")
        # '?D,*,1' while running continuously - the volume field is '*', not a number.
        raw_volume = self._field(response, 1)
        volume = 0.0 if raw_volume.strip("-") == "*" else float(raw_volume)
        return volume, self._field(response, 2) == "1"

    def read_volume_dispensed(self) -> float:
        """Return the volume dispensed by the current or last dispense, in ml (``R``)."""
        return float(self._transact("R"))

    def stop(self) -> float:
        """Stop dispensing and return the volume dispensed, in ml (``X`` -> ``*DONE,v``)."""
        return float(self._field(self._transact("X", done_terminates=True), 1))

    def pause(self) -> None:
        """Toggle pause on the dispense in progress (``P``).

        The hardware command is a toggle; prefer the driver's ``set_paused``
        for an idempotent set.
        """
        self._transact("P")

    def get_pause_status(self) -> bool:
        """Return True if the dispense in progress is paused (``P,?``)."""
        return self._field(self._transact("P,?"), 1) == "1"

    def invert(self) -> None:
        """Toggle the pump's dispensing direction (``Invert``). Retained across power loss."""
        self._transact("Invert")

    def get_invert_status(self) -> bool:
        """Return True if the dispensing direction is inverted (``Invert,?``)."""
        return self._field(self._transact("Invert,?"), 1) == "1"

    # Volume totals

    def get_total_volume(self) -> float:
        """Return the net total volume pumped in ml (``TV,?``). Reverse dispensing subtracts."""
        return float(self._field(self._transact("TV,?"), 1))

    def get_absolute_total_volume(self) -> float:
        """Return the total volume pumped in ml ignoring direction (``ATV,?``)."""
        return float(self._field(self._transact("ATV,?"), 1))

    def clear_total_volume(self) -> None:
        """Reset both total-volume counters to zero (``Clear``)."""
        self._transact("Clear")

    # Calibration and diagnostics

    def calibrate(self, volume: float) -> None:
        """Calibrate to the volume actually delivered by the last dispense (``Cal,v``)."""
        self._transact(f"Cal,{_fmt(volume)}")

    def clear_calibration(self) -> None:
        """Erase all stored calibration data (``Cal,clear``)."""
        self._transact("Cal,clear")

    def get_calibration_status(self) -> int:
        """Return 0 uncalibrated, 1 fixed volume, 2 volume/time, or 3 both (``Cal,?``)."""
        return int(self._field(self._transact("Cal,?"), 1))

    def get_pump_voltage(self) -> float:
        """Return the motor supply voltage in volts (``PV,?``)."""
        return float(self._field(self._transact("PV,?"), 1))

    def get_info(self) -> str:
        """Return the device type and firmware version (``i`` -> ``?i,PMP,1.1``)."""
        return self._transact("i")

    def get_status(self) -> str:
        """Return the restart reason and Vcc voltage (``Status`` -> ``?Status,P,5.038``)."""
        return self._transact("Status")

    # Circuit housekeeping

    def find(self) -> None:
        """Blink the LED rapidly to locate the physical circuit (``Find``).

        Also disables continuous reporting, per the datasheet - harmless here,
        since the driver already turns it off at startup. Any subsequent
        command ends the blinking.
        """
        self._transact("Find")

    def set_led(self, enabled: bool) -> None:
        """Turn the status LED on or off (``L,1`` / ``L,0``)."""
        self._transact(f"L,{1 if enabled else 0}")

    def get_led(self) -> bool:
        """Return True if the status LED is currently on (``L,?``)."""
        return self._field(self._transact("L,?"), 1) == "1"

    def set_protocol_lock(self, enabled: bool) -> None:
        """Lock the circuit to its current protocol, blocking UART/I2C switching (``Plock``)."""
        self._transact(f"Plock,{1 if enabled else 0}")

    def get_protocol_lock(self) -> bool:
        """Return True if the protocol lock is enabled (``Plock,?``)."""
        return self._field(self._transact("Plock,?"), 1) == "1"

    def sleep(self) -> None:
        """Put the circuit into low-power sleep (``Sleep``).

        Drops the control system from ~13.4mA to ~0.415mA at 5V. This is the
        *control system* only - it does not cut the 12-24V motor supply. Call
        :meth:`wake` before issuing further commands.
        """
        self._transact("Sleep")

    def wake(self) -> None:
        """Wake the circuit from sleep mode.

        The byte that wakes a sleeping EZO is consumed doing so and may not be
        executed as a command (the circuit answers ``*WA`` instead of the
        expected reply), so this sends a throwaway ``Status`` and tolerates
        getting nothing usable back. Issue the real command afterwards.
        """
        try:
            self._transact("Status")
        except (IOError, ValueError):
            pass  # the wake byte was swallowed; the circuit is awake regardless
