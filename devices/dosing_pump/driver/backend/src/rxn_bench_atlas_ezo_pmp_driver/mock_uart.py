r"""In-memory mock serial port emulating the Atlas Scientific EZO-PMP UART protocol.

Lets the real driver stack (AtlasScientificEZOPumpUart -> AtlasDosingPump) run
end-to-end without hardware. It answers the same ASCII commands a physical
EZO-PMP would over serial - CR-terminated data lines framed by ``*OK`` / ``*ER``
response codes - behind the minimal ``write`` / ``read_until`` port interface the
driver depends on.

Dispensing is simulated against an injectable clock, so a test can advance time
and watch a dose progress and complete rather than only checking that the right
bytes went out:

    from rxn_bench_atlas_ezo_pmp_driver.atlas_dosing_pump import AtlasDosingPump
    from rxn_bench_atlas_ezo_pmp_driver.atlas_scientific_uart_driver import AtlasScientificEZOPumpUart
    from rxn_bench_atlas_ezo_pmp_driver.mock_uart import MockEZOPumpUart

    clock = [0.0]
    port = MockEZOPumpUart(clock=lambda: clock[0])
    pump = AtlasDosingPump(AtlasScientificEZOPumpUart(port))
    pump.dispense_volume(10.0)
    clock[0] += 60.0                  # one minute later
    pump.read_volume_dispensed()      # partial or complete, per the flow rate
"""
from __future__ import annotations

import time
from collections import deque

from rxn_bench_atlas_ezo_pmp_driver.ezo_pmp_commands import MIN_DISPENSE_ML

_CR = b"\r"

# Open-loop rate for continuous dispensing (``D,*``), matching the datasheet's
# ~105 ml/min with the supplied tubing. Distinct from - and higher than - the
# metered ceiling ``DC,?`` reports for constant-rate mode.
_CONTINUOUS_RATE = 105.0


class MockEZOPumpUart:
    """EZO-PMP serial protocol emulator behind the write/read_until port interface."""

    def __init__(
        self,
        max_flow_rate: float = 58.5,
        pump_voltage: float = 13.86,
        clock=time.monotonic,
    ) -> None:
        """
        Args:
            max_flow_rate: Metered ceiling reported by ``DC,?``; requests above it
                get ``*TOOFAST``. Defaults to the datasheet's example value. Note
                this is deliberately *below* ``_CONTINUOUS_RATE``: the pump can
                only regulate to a fraction of its open-loop top speed, and the
                real figure depends on calibration.
            pump_voltage: Motor supply voltage reported by ``PV,?``.
            clock: Monotonic seconds source. Inject a fake to drive dispense
                progress deterministically in tests.
        """
        self.max_flow_rate = max_flow_rate
        self.pump_voltage = pump_voltage
        self._clock = clock

        # Wire token, not a bool: '*' reports every second, '1' only while
        # pumping, '0' off. '*' is the pump's power-on default.
        self.continuous_reporting = "*"
        self.paused = False
        self.inverted = False
        self.led = True
        self.protocol_lock = False
        self.asleep = False
        self.finding = False
        self.calibration = 0
        self.total_volume = 0.0
        self.absolute_total_volume = 0.0
        self.commands: list[str] = []       # every command written, for assertions
        self._outbox: deque[bytes] = deque()

        # Active dispense state
        self._target: float | None = None   # ml to deliver; None = run indefinitely
        self._rate = 0.0                    # ml/min, always positive
        self._sign = 1                      # +1 forward, -1 reverse
        self._dispensed = 0.0               # ml delivered in this dispense
        self._running = False
        self._last_requested: float | str = 0.0
        self._mark: float | None = None     # clock reading at last _advance
        self._done_volume: float | None = None  # queued unsolicited *DONE payload

    # Port interface

    def write(self, data: bytes) -> None:
        """Parse a CR-terminated ASCII command and queue the reply line(s)."""
        cmd = data.rstrip(_CR).decode("ascii")
        self.commands.append(cmd)
        self._advance()
        lines = self._respond(cmd)
        # An unsolicited *DONE lands ahead of the real reply on purpose: that is
        # the ordering most likely to confuse a reader, so the driver is held to
        # handling it.
        if self._done_volume is not None and cmd != "X":
            lines = [f"*DONE,{self._done_volume:.2f}"] + lines
            self._done_volume = None
        for line in lines:
            self._outbox.append(line.encode("ascii") + _CR)

    def read_until(self, expected: bytes = _CR) -> bytes:
        """Return the next queued reply line, or b'' when nothing is queued."""
        if self._outbox:
            return self._outbox.popleft()
        return b""

    def reset_input_buffer(self) -> None:
        """Discard any queued-but-unread reply lines (mirrors serial.Serial)."""
        self._outbox.clear()

    # Dispense simulation

    def _advance(self) -> None:
        """Credit volume for the time elapsed since the last call."""
        now = self._clock()
        if not self._running or self._mark is None:
            self._mark = now
            return
        elapsed_min = max(now - self._mark, 0.0) / 60.0
        self._mark = now
        if self.paused:
            return
        self._dispensed += self._rate * elapsed_min
        if self._target is not None and self._dispensed >= self._target:
            self._dispensed = self._target
            self._finish()

    def _finish(self) -> None:
        """Complete the active dispense and bank it into the totals."""
        delivered = self._dispensed * self._sign
        self.total_volume += delivered
        self.absolute_total_volume += abs(delivered)
        self._running = False
        self._done_volume = delivered

    def _start(self, target: float | None, rate: float, sign: int) -> None:
        self._target = target
        self._rate = abs(rate)
        self._sign = sign
        self._dispensed = 0.0
        self._running = True
        self.paused = False
        self._mark = self._clock()

    def _volume_now(self) -> float:
        return self._dispensed * self._sign

    # Command dispatch

    def _respond(self, cmd: str) -> list[str]:
        """Return the reply line(s) for a command: a data line (if any) then ``*OK``, or ``*ER``."""
        if self.asleep:
            # The waking byte is consumed doing so and is *not* executed - the
            # circuit answers only *WA. Modelled faithfully so the driver's
            # wake() path is exercised rather than assumed.
            self.asleep = False
            return ["*WA"]
        self.finding = False  # any command terminates Find's blinking
        head, _, arg = cmd.partition(",")
        handler = getattr(self, f"_cmd_{head.lower()}", None)
        if handler is None:
            return ["*ER"]
        return handler(arg)

    def _cmd_c(self, arg: str) -> list[str]:
        if arg == "?":
            return [f"?C,{self.continuous_reporting}", "*OK"]
        if arg in ("0", "1", "*"):
            self.continuous_reporting = arg
            return ["*OK"]
        return ["*ER"]

    def _cmd_r(self, arg: str) -> list[str]:
        return [f"{self._volume_now():.2f}", "*OK"]

    def _cmd_d(self, arg: str) -> list[str]:
        if arg == "?":
            vol = self._last_requested
            shown = vol if isinstance(vol, str) else f"{vol:.2f}"
            return [f"?D,{shown},{1 if self._running else 0}", "*OK"]
        if arg in ("*", "-*"):
            self._last_requested = arg
            self._start(None, _CONTINUOUS_RATE, -1 if arg == "-*" else 1)
            return ["*OK"]

        volume_text, _, minutes_text = arg.partition(",")
        try:
            volume = float(volume_text)
        except ValueError:
            return ["*ER"]
        if abs(volume) < MIN_DISPENSE_ML:
            return ["*MINVOL", "*ER"]

        if minutes_text:
            try:
                minutes = float(minutes_text)
            except ValueError:
                return ["*ER"]
            if minutes <= 0:
                return ["*ER"]
            rate = abs(volume) / minutes
            if rate > self.max_flow_rate:
                return ["*TOOFAST", "*ER"]
        else:
            rate = _CONTINUOUS_RATE

        self._last_requested = volume
        self._start(abs(volume), rate, 1 if volume >= 0 else -1)
        return ["*OK"]

    def _cmd_dc(self, arg: str) -> list[str]:
        if arg == "?":
            return [f"?MAXRATE,{self.max_flow_rate}", "*OK"]
        rate_text, _, minutes_text = arg.partition(",")
        try:
            rate = float(rate_text)
        except ValueError:
            return ["*ER"]
        if abs(rate) > self.max_flow_rate:
            return ["*TOOFAST", "*ER"]
        sign = 1 if rate >= 0 else -1
        if minutes_text == "*":
            target = None
        else:
            try:
                target = abs(rate) * float(minutes_text)
            except ValueError:
                return ["*ER"]
        self._last_requested = 0.0 if target is None else target * sign
        self._start(target, rate, sign)
        return ["*OK"]

    def _cmd_x(self, arg: str) -> list[str]:
        volume = self._volume_now()
        if self._running:
            self._finish()
        # Reported as this command's reply, so it must not also be replayed as
        # an unsolicited *DONE on the next command.
        self._done_volume = None
        return [f"*DONE,{volume:.2f}"]

    def _cmd_p(self, arg: str) -> list[str]:
        if arg == "?":
            return [f"?P,{1 if self.paused else 0}", "*OK"]
        if arg:
            return ["*ER"]
        self.paused = not self.paused
        return ["*OK"]

    def _cmd_invert(self, arg: str) -> list[str]:
        if arg == "?":
            return [f"?Invert,{1 if self.inverted else 0}", "*OK"]
        if arg:
            return ["*ER"]
        self.inverted = not self.inverted
        return ["*OK"]

    def _cmd_tv(self, arg: str) -> list[str]:
        if arg != "?":
            return ["*ER"]
        return [f"?TV,{self.total_volume:.2f}", "*OK"]

    def _cmd_atv(self, arg: str) -> list[str]:
        if arg != "?":
            return ["*ER"]
        return [f"?ATV,{self.absolute_total_volume:.2f}", "*OK"]

    def _cmd_clear(self, arg: str) -> list[str]:
        self.total_volume = 0.0
        self.absolute_total_volume = 0.0
        return ["*OK"]

    def _cmd_pv(self, arg: str) -> list[str]:
        if arg != "?":
            return ["*ER"]
        return [f"?PV,{self.pump_voltage:.2f}", "*OK"]

    def _cmd_cal(self, arg: str) -> list[str]:
        if arg == "?":
            return [f"?Cal,{self.calibration}", "*OK"]
        if arg == "clear":
            self.calibration = 0
            return ["*OK"]
        try:
            float(arg)
        except ValueError:
            return ["*ER"]
        # 1 = fixed volume, 2 = volume/time, 3 = both. A plain volume dispense
        # calibrates the fixed-volume mode.
        self.calibration = 3 if self.calibration == 2 else 1
        return ["*OK"]

    def _cmd_find(self, arg: str) -> list[str]:
        self.finding = True
        self.continuous_reporting = "0"   # Find disables continuous mode
        return ["*OK"]

    def _cmd_l(self, arg: str) -> list[str]:
        if arg == "?":
            return [f"?L,{1 if self.led else 0}", "*OK"]
        if arg in ("0", "1"):
            self.led = arg == "1"
            return ["*OK"]
        return ["*ER"]

    def _cmd_plock(self, arg: str) -> list[str]:
        if arg == "?":
            return [f"?Plock,{1 if self.protocol_lock else 0}", "*OK"]
        if arg in ("0", "1"):
            self.protocol_lock = arg == "1"
            return ["*OK"]
        return ["*ER"]

    def _cmd_sleep(self, arg: str) -> list[str]:
        self.asleep = True
        return ["*OK", "*SL"]

    def _cmd_i(self, arg: str) -> list[str]:
        return ["?i,PMP,1.1", "*OK"]

    def _cmd_status(self, arg: str) -> list[str]:
        return ["?Status,P,5.038", "*OK"]
