"""Test doubles for MotionClientProtocol - shared across engine/homing/controller tests.

Unlike MockMoonrakerClient (which simulates real travel time for manual/dev use),
this fake has no delay and records every call so tests can assert call order.
"""


class FakeMotionClient:
    """In-memory MotionClientProtocol double: no delay, records every call."""

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.calls: list[tuple[str, dict]] = []
        self._x, self._y, self._z = x, y, z
        self._homed_axes = ""
        self._state = "ready"

    def set_kinematic_position(
        self, x: float | None = None, y: float | None = None, z: float | None = None
    ) -> None:
        self.calls.append(("set_kinematic_position", {"x": x, "y": y, "z": z}))
        if x is not None:
            self._x = x
        if y is not None:
            self._y = y
        if z is not None:
            self._z = z

    def home(self, axes: str = "XY") -> None:
        self.calls.append(("home", {"axes": axes}))
        axes = axes.upper()
        if "X" in axes:
            self._x = 0.0
        if "Y" in axes:
            self._y = 0.0
        if "Z" in axes:
            self._z = 0.0
        self._homed_axes = axes.lower()

    def move(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None:
        self.calls.append(("move", {"x": x, "y": y, "z": z, "speed": speed}))
        if x is not None:
            self._x = x
        if y is not None:
            self._y = y
        if z is not None:
            self._z = z

    def jog(
        self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, speed: float | None = None
    ) -> None:
        self.calls.append(("jog", {"dx": dx, "dy": dy, "dz": dz, "speed": speed}))
        self._x += dx
        self._y += dy
        self._z += dz

    def get_position(self) -> dict[str, float]:
        return {"x": self._x, "y": self._y, "z": self._z}

    def get_homed_axes(self) -> str:
        return self._homed_axes

    def get_axis_limits(self) -> dict[str, tuple[float, float]]:
        return {"x": (0.0, 350.0), "y": (0.0, 350.0), "z": (0.0, 340.0)}

    def get_state(self) -> str:
        return self._state

    def gcode(self, script: str) -> None:
        self.calls.append(("gcode", {"script": script}))
