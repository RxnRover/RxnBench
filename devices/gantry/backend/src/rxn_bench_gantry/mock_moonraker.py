"""
In-memory mock for MoonrakerClient. Simulates motion with time-proportional delays.
Enable with RXN_BENCH_MOCK=1.
"""
import math
import threading
import time


class MockMoonrakerClient:
    """In-memory motion simulator. Blocks proportionally to distance (max 2 s per move)."""

    def __init__(self, host: str = "mock", port: int = 0, default_speed: float = 3000.0):
        """Initialise the simulator at the origin.

        Args:
            host: Ignored - present for API symmetry with MoonrakerClient.
            port: Ignored - present for API symmetry with MoonrakerClient.
            default_speed: Simulated feed rate in mm/min used to calculate travel time.
        """
        self._x = 0.0
        self._y = 0.0
        self._z = 0.0
        self._homed_axes = ""
        self._state = "ready"
        self._lock = threading.Lock()
        self.default_speed = default_speed

    def _travel_time(
        self,
        tx: float | None,
        ty: float | None,
        tz: float | None,
        speed: float,
    ) -> float:
        """Return simulated travel time in seconds (capped at 2 s)."""
        with self._lock:
            dx = (tx - self._x) if tx is not None else 0.0
            dy = (ty - self._y) if ty is not None else 0.0
            dz = (tz - self._z) if tz is not None else 0.0
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        return min(dist / (speed / 60.0), 2.0)

    def _apply(self, tx: float | None, ty: float | None, tz: float | None) -> None:
        with self._lock:
            if tx is not None:
                self._x = tx
            if ty is not None:
                self._y = ty
            if tz is not None:
                self._z = tz

    def set_kinematic_position(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        """Update the simulated position for the given axes without a travel delay."""
        self._apply(x, y, z)

    def home(self, axes: str = "XY") -> None:
        """Simulate homing by resetting the specified axes to 0 after a 1 s delay.

        Args:
            axes: String of axis letters to home, e.g. ``'XY'``.
        """
        axes = axes.upper()
        time.sleep(1.0)
        with self._lock:
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
        """Simulate an absolute move, blocking for a distance-proportional duration.

        Args:
            x: Target X in mm, or None to skip.
            y: Target Y in mm, or None to skip.
            z: Target Z in mm, or None to skip.
            speed: Simulated feed rate in mm/min.
        """
        spd = speed or self.default_speed
        self._state = "printing"
        time.sleep(self._travel_time(x, y, z, spd))
        self._apply(x, y, z)
        self._state = "ready"

    def jog(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        speed: float | None = None,
    ) -> None:
        """Simulate a relative move, blocking for a distance-proportional duration.

        Args:
            dx: X displacement in mm.
            dy: Y displacement in mm.
            dz: Z displacement in mm.
            speed: Simulated feed rate in mm/min.
        """
        with self._lock:
            tx = self._x + dx
            ty = self._y + dy
            tz = self._z + dz
        spd = speed or self.default_speed
        self._state = "printing"
        time.sleep(self._travel_time(tx, ty, tz, spd))
        self._apply(tx, ty, tz)
        self._state = "ready"

    def get_position(self) -> dict[str, float]:
        """Return the current simulated XYZ position."""
        with self._lock:
            return {"x": self._x, "y": self._y, "z": self._z}

    def get_homed_axes(self) -> str:
        """Return which axes have been simulated-homed, e.g. ``'xy'`` or ``''``."""
        return self._homed_axes

    def get_axis_limits(self) -> dict[str, tuple[float, float]]:
        """Return fixed simulated axis limits (350 x 350 x 340 mm)."""
        return {"x": (0.0, 350.0), "y": (0.0, 350.0), "z": (0.0, 340.0)}

    def get_state(self) -> str:
        """Return the simulated state string: ``'ready'`` or ``'printing'``."""
        return self._state

    def gcode(self, script: str) -> None:
        """Simulate GCode execution with a minimal 50 ms delay."""
        time.sleep(0.05)
