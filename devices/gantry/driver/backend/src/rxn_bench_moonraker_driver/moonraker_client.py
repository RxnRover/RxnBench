"""REST client for the Moonraker API, wrapping printer GCode execution."""
import requests

# (connect, read) timeouts in seconds. A request that never times out would
# hang the whole server: motion commands run while holding the feature-level
# hardware lock, so one wedged HTTP call blocks every subsequent RPC.
_QUERY_TIMEOUT = (3.05, 10.0)
# GCode scripts block until motion completes (M400) - homing and long slow
# moves legitimately take minutes, so the read timeout is generous but finite.
_GCODE_TIMEOUT = (3.05, 600.0)


class MoonrakerClient:
    """HTTP client for the Moonraker printer API. All move commands block until the motion is complete (M400)."""

    def __init__(self, host: str, port: int = 7125, default_speed: float = 3000.0):
        """Connect to a Moonraker instance.

        Args:
            host: Hostname or IP address of the Moonraker server.
            port: HTTP port for the Moonraker API (default 7125).
            default_speed: Fallback feed rate in mm/min when no speed is provided.
        """
        self._base = f"http://{host}:{port}"
        self.default_speed = default_speed  # mm/min

    def set_kinematic_position(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        """Tell Klipper the current position for any axes without physically homing."""
        params = " ".join(
            f"{axis}={val:.3f}"
            for axis, val in [("X", x), ("Y", y), ("Z", z)]
            if val is not None
        )
        self.gcode(f"SET_KINEMATIC_POSITION {params}")

    def home(self, axes: str = "XY") -> None:
        """Home the specified axes. Never pass Z - no probe is attached.

        Args:
            axes: String of axis letters to home, e.g. ``'XY'`` or ``'X'``.
        """
        axes_spaced = " ".join(axes.upper())  # "XY" -> "X Y" for Klipper's param parser
        self.gcode(f"G28 {axes_spaced}\nM400")

    def move(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None:
        """Move to absolute machine coordinates (mm) and wait until done."""
        coords = " ".join(
            f"{axis}{val:.3f}"
            for axis, val in [("X", x), ("Y", y), ("Z", z)]
            if val is not None
        )
        feed = speed if speed is not None else self.default_speed
        self.gcode(f"G90\nG0 {coords} F{feed:.0f}\nM400")

    def jog(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        speed: float | None = None,
    ) -> None:
        """Move relative to current position. No clearance sequence."""
        coords = " ".join(
            f"{axis}{val:.3f}"
            for axis, val in [("X", dx), ("Y", dy), ("Z", dz)]
            if val != 0.0
        )
        feed = speed if speed is not None else self.default_speed
        self.gcode(f"G91\nG0 {coords} F{feed:.0f}\nG90\nM400")

    def get_position(self) -> dict[str, float]:
        """Return the current machine position."""
        r = requests.get(f"{self._base}/printer/objects/query?toolhead", timeout=_QUERY_TIMEOUT)
        r.raise_for_status()
        pos = r.json()["result"]["status"]["toolhead"]["position"]
        return {"x": pos[0], "y": pos[1], "z": pos[2]}

    def get_homed_axes(self) -> str:
        """Return which axes are currently homed, e.g. 'xy', 'xyz', or ''."""
        r = requests.get(f"{self._base}/printer/objects/query?toolhead", timeout=_QUERY_TIMEOUT)
        r.raise_for_status()
        return r.json()["result"]["status"]["toolhead"].get("homed_axes", "")

    def get_axis_limits(self) -> dict[str, tuple[float, float]]:
        """Return Klipper's configured axis limits as {axis: (min, max)}."""
        r = requests.get(f"{self._base}/printer/objects/query?toolhead", timeout=_QUERY_TIMEOUT)
        r.raise_for_status()
        status = r.json()["result"]["status"]["toolhead"]
        mins = status["axis_minimum"]   # [x, y, z, e]
        maxs = status["axis_maximum"]
        return {
            "x": (mins[0], maxs[0]),
            "y": (mins[1], maxs[1]),
            "z": (mins[2], maxs[2]),
        }

    def get_state(self) -> str:
        """Return the Klipper state string e.g. 'ready', 'error'."""
        r = requests.get(f"{self._base}/printer/info", timeout=_QUERY_TIMEOUT)
        r.raise_for_status()
        return r.json()["result"]["state"]

    def gcode(self, script: str) -> None:
        """Send any raw GCode string to Klipper and wait for it to finish."""
        r = requests.post(
            f"{self._base}/printer/gcode/script",
            json={"script": script},
            timeout=_GCODE_TIMEOUT,
        )
        r.raise_for_status()
