r"""In-memory mock serial port emulating the Atlas Scientific EZO-pH UART protocol.

The UART counterpart to :mod:`rxn_bench_ph.mock_i2c`: it lets the real driver
stack (AtlasScientificEZOUart -> AtlasPHSensor) run end-to-end without hardware.
It answers the same ASCII commands a physical EZO circuit would over serial -
CR-terminated data lines framed by ``*OK`` / ``*ER`` response codes - behind the
minimal ``write`` / ``read_until`` port interface the driver depends on.

    from rxn_bench_ph.atlas_ph_sensor import AtlasPHSensor
    from rxn_bench_ph.atlas_scientific_uart_driver import AtlasScientificEZOUart
    from rxn_bench_ph.mock_uart import MockEZOUart

    sensor = AtlasPHSensor(driver=AtlasScientificEZOUart(MockEZOUart(ph=7.2)))
    sensor.read().value  # 7.2
"""
from __future__ import annotations

from collections import deque

_CR = b"\r"


class MockEZOUart:
    """EZO-pH serial protocol emulator behind the write/read_until port interface."""

    def __init__(self, ph: float = 7.004, acid_slope: float = 99.7, base_slope: float = 100.3):
        """
        Args:
            ph: Value returned for pH read commands. Mutable via ``port.ph = ...``.
            acid_slope: Acid slope percentage reported by ``Slope,?``.
            base_slope: Base slope percentage reported by ``Slope,?``.
        """
        self.ph = ph
        self.acid_slope = acid_slope
        self.base_slope = base_slope
        self.temperature = 25.0
        self.led = True
        self.continuous = True
        self.calibration_points: set[str] = set()
        self.commands: list[str] = []              # every command written, for assertions
        self._outbox: deque[bytes] = deque()       # queued CR-terminated reply lines

    def write(self, data: bytes) -> None:
        """Parse a CR-terminated ASCII command and queue the reply line(s)."""
        cmd = data.rstrip(_CR).decode("ascii")
        self.commands.append(cmd)
        for line in self._respond(cmd):
            self._outbox.append(line.encode("ascii") + _CR)

    def read_until(self, expected: bytes = _CR) -> bytes:
        """Return the next queued reply line, or b'' when nothing is queued."""
        if self._outbox:
            return self._outbox.popleft()
        return b""

    def reset_input_buffer(self) -> None:
        """Discard any queued-but-unread reply lines (mirrors serial.Serial)."""
        self._outbox.clear()

    def _respond(self, cmd: str) -> list[str]:
        """Return the reply line(s) for a command: a data line (if any) then ``*OK``, or ``*ER``."""
        if cmd == "R":
            return [f"{self.ph:.3f}", "*OK"]
        if cmd.startswith("Cal,"):
            arg = cmd.split(",")[1]
            if arg == "clear":
                self.calibration_points.clear()
                return ["*OK"]
            if arg == "?":
                return [f"?Cal,{len(self.calibration_points)}", "*OK"]
            if arg in ("mid", "low", "high"):
                self.calibration_points.add(arg)
                return ["*OK"]
            return ["*ER"]
        if cmd == "Slope,?":
            return [f"?Slope,{self.acid_slope},{self.base_slope}", "*OK"]
        if cmd == "T,?":
            return [f"?T,{self.temperature}", "*OK"]
        if cmd.startswith("T,"):
            self.temperature = float(cmd.split(",")[1])
            return ["*OK"]
        if cmd == "C,?":
            return [f"?C,{1 if self.continuous else 0}", "*OK"]
        if cmd.startswith("C,"):
            self.continuous = cmd.split(",")[1] == "1"
            return ["*OK"]
        if cmd == "Status":
            return ["?Status,P,3.83", "*OK"]
        if cmd == "i":
            return ["?i,pH,2.12", "*OK"]
        if cmd == "L,?":
            return [f"?L,{1 if self.led else 0}", "*OK"]
        if cmd.startswith("L,"):
            self.led = cmd.split(",")[1] == "1"
            return ["*OK"]
        if cmd in ("Find", "Sleep"):
            return ["*OK"]
        return ["*ER"]
