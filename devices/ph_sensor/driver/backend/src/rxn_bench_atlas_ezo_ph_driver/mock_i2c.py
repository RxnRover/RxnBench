"""In-memory mock I2C bus emulating the Atlas Scientific EZO-pH command protocol.

Lets the real driver stack (AtlasScientificEZO -> AtlasPHSensor) run end-to-end
without hardware: MockI2CBus answers the same ASCII commands a physical EZO
circuit would, with the standard status byte prefix and null padding.

    from rxn_bench_atlas_ezo_ph_driver.atlas_ph_sensor import AtlasPHSensor
    from rxn_bench_atlas_ezo_ph_driver.mock_i2c import MockI2CBus

    sensor = AtlasPHSensor(MockI2CBus(ph=7.2))
    sensor.read().value  # 7.2
"""
from __future__ import annotations

_STATUS_OK = b"\x01"
_STATUS_SYNTAX_ERR = b"\x02"


class MockI2CBus:
    """EZO-pH protocol emulator behind the write/read bus interface."""

    def __init__(self, ph: float = 7.004, acid_slope: float = 99.7, base_slope: float = 100.3):
        """
        Args:
            ph: Value returned for pH read commands. Mutable via ``bus.ph = ...``.
            acid_slope: Acid slope percentage reported by ``Slope,?``.
            base_slope: Base slope percentage reported by ``Slope,?``.
        """
        self.ph = ph
        self.acid_slope = acid_slope
        self.base_slope = base_slope
        self.temperature = 25.0
        self.led = True
        self.calibration_points: set[str] = set()
        self.commands: list[str] = []          # every command written, for assertions
        self._response: bytes = _STATUS_OK

    def write(self, address: int, data: bytes) -> None:
        """Record the ASCII command and prepare the response for the next read."""
        cmd = data.decode("ascii")
        self.commands.append(cmd)
        self._response = self._respond(cmd)

    def read(self, address: int, num_bytes: int) -> bytes:
        """Return the response to the last command, null-padded to num_bytes."""
        return self._response.ljust(num_bytes, b"\x00")

    def _respond(self, cmd: str) -> bytes:
        def ok(payload: str = "") -> bytes:
            return _STATUS_OK + payload.encode("ascii")

        if cmd == "R":
            return ok(f"{self.ph:.3f}")
        if cmd.startswith("Cal,"):
            arg = cmd.split(",")[1]
            if arg == "clear":
                self.calibration_points.clear()
                return ok()
            if arg == "?":
                return ok(f"?Cal,{len(self.calibration_points)}")
            if arg in ("mid", "low", "high"):
                self.calibration_points.add(arg)
                return ok()
            return _STATUS_SYNTAX_ERR
        if cmd == "Slope,?":
            return ok(f"?Slope,{self.acid_slope},{self.base_slope}")
        if cmd == "T,?":
            return ok(f"?T,{self.temperature}")
        if cmd.startswith("T,"):
            self.temperature = float(cmd.split(",")[1])
            return ok()
        if cmd == "Status":
            return ok("?Status,P,3.83")
        if cmd == "i":
            return ok("?i,pH,2.12")
        if cmd == "L,?":
            return ok(f"?L,{1 if self.led else 0}")
        if cmd.startswith("L,"):
            self.led = cmd.split(",")[1] == "1"
            return ok()
        if cmd in ("Find", "Sleep"):
            return ok()
        return _STATUS_SYNTAX_ERR
