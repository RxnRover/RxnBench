"""
Thin layer above MoonrakerClient. This is what the rest of the system
talks to for all motion.

Adds:
- Active toolhead tracking - loads geometry from YAML and applies XY offsets
  and Z tip compensation on every move.
- Safe travel sequence - always raises to clearance_z before moving XY,
  then lowers to the target Z.
- Bounds checking - enforces machine limits and toolhead footprint before
  sending any GCode.
- Guided homing procedure - supports both auto (endstop) and manual homing
  for when a toolhead is already mounted.

Author: John Brittain
Date: Jun 17 2026
"""
from pathlib import Path
from .moonraker_client import MoonrakerClient
from chem_bench.io.toolheads.toolhead_config import ToolheadConfig, ToolheadGeometry
from chem_bench.io.errors import MotionLimitError

_TOOLHEADS_DIR = Path(__file__).parent.parent / "toolheads"

# During manual homing every jog pre-resets the kinematic position so the
# destination always lands here — guaranteed to be within any reasonable
# Klipper position_max while still allowing ±100 mm steps.
_HOMING_SAFE_MID = 175.0


class MotionPlatformController:

    def __init__(
        self,
        moonraker_host: str,
        clearance_z: float = 50.0,
        x_min: float = 0.0,
        x_max: float = 350.0,
        y_min: float = 0.0,
        y_max: float = 350.0,
        z_min: float = 0.0,
        z_max: float = 340.0,
    ):
        self._client = MoonrakerClient(moonraker_host)
        self._clearance_z = clearance_z
        self._x_min = x_min
        self._x_max = x_max
        self._y_min = y_min
        self._y_max = y_max
        self._z_min = z_min
        self._z_max = z_max
        self._toolhead: ToolheadGeometry | None = None
        self._toolhead_name: str = ""
        self._toolhead_display_name: str = ""
        self._homing_active: bool = False
        # Accumulated net displacement per axis since the last confirm_*_min call.
        # Used by confirm_x_max / confirm_y_max because the pre-jog kinematic
        # reset trick makes Klipper's reported position meaningless during homing.
        self._homing_accum: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0}

    def set_toolhead(self, name: str) -> None:
        """Load a toolhead config by name and use its geometry for future moves."""
        cfg = ToolheadConfig.load(name)
        self._toolhead = cfg.geometry
        self._toolhead_name = cfg.name
        self._toolhead_display_name = cfg.display_name

    def clear_toolhead(self) -> None:
        """Remove the active toolhead, reverting to bare carriage geometry."""
        self._toolhead = None
        self._toolhead_name = ""
        self._toolhead_display_name = ""

    def get_toolhead(self) -> ToolheadGeometry | None:
        return self._toolhead

    def get_toolhead_name(self) -> str:
        return self._toolhead_name

    def get_toolhead_display_name(self) -> str:
        return self._toolhead_display_name

    @staticmethod
    def list_toolheads() -> list[tuple[str, str]]:
        """Return [(name, display_name), …] for every installed toolhead config."""
        results = []
        for folder in sorted(_TOOLHEADS_DIR.iterdir()):
            yaml_path = folder / f"{folder.name}_toolhead.yaml"
            if yaml_path.exists():
                try:
                    cfg = ToolheadConfig.from_yaml(yaml_path)
                    results.append((cfg.name, cfg.display_name))
                except Exception:
                    pass
        return results
    
    def _check_bounds(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        """Raise MotionLimitError if any axis would leave the safe envelope."""
        half_fx = (self._toolhead.footprint_x / 2) if self._toolhead else 0.0
        half_fy = (self._toolhead.footprint_y / 2) if self._toolhead else 0.0
        tip_z   = self._toolhead.tip_offset_z if self._toolhead else 0.0

        if x is not None:
            if x - half_fx < self._x_min or x + half_fx > self._x_max:
                raise MotionLimitError(
                    f"X={x:.1f} with footprint {half_fx*2:.1f}mm exceeds X limits "
                    f"[{self._x_min}, {self._x_max}]"
                )
        if y is not None:
            if y - half_fy < self._y_min or y + half_fy > self._y_max:
                raise MotionLimitError(
                    f"Y={y:.1f} with footprint {half_fy*2:.1f}mm exceeds Y limits "
                    f"[{self._y_min}, {self._y_max}]"
                )
        if z is not None:
            if z > self._z_max:
                raise MotionLimitError(f"Z={z:.1f} exceeds maximum {self._z_max}mm")
            if z - tip_z < self._z_min:
                raise MotionLimitError(
                    f"Z={z:.1f} would put tool tip at {z - tip_z:.1f}mm, "
                    f"below minimum {self._z_min}mm"
                )

    # --- homing ---

    def home_auto(self) -> None:
        """Home XY via endstops. Only safe when no toolhead is mounted."""
        if "z" in self._client.get_homed_axes().lower():
            self._client.move(z=self._clearance_z)
        self._client.home("XY")

    def start_manual_homing(self) -> None:
        """Begin manual homing with a toolhead mounted.

        Sets kinematic position to _HOMING_SAFE_MID on all axes so subsequent
        jogs always have room in both directions regardless of Klipper's
        configured position_max. Bounds checking is suspended until finish_homing().
        """
        self._homing_active = True
        self._homing_accum = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._client.set_kinematic_position(
            x=_HOMING_SAFE_MID, y=_HOMING_SAFE_MID, z=_HOMING_SAFE_MID
        )

    def confirm_x_min(self) -> None:
        """Declare the current X position as X=0 and store it as the X minimum."""
        self._client.set_kinematic_position(x=_HOMING_SAFE_MID)
        self._x_min = 0.0
        self._homing_accum["x"] = 0.0

    def confirm_x_max(self) -> None:
        """Record the accumulated X travel from X_min as the X maximum."""
        self._x_max = abs(self._homing_accum["x"])
        self._homing_accum["x"] = 0.0

    def confirm_y_min(self) -> None:
        """Declare the current Y position as Y=0 and store it as the Y minimum."""
        self._client.set_kinematic_position(y=_HOMING_SAFE_MID)
        self._y_min = 0.0
        self._homing_accum["y"] = 0.0

    def confirm_y_max(self) -> None:
        """Record the accumulated Y travel from Y_min as the Y maximum."""
        self._y_max = abs(self._homing_accum["y"])
        self._homing_accum["y"] = 0.0

    def confirm_z_reference(self) -> None:
        """Declare the current Z position as Z=0."""
        self._client.set_kinematic_position(z=0)
        self._homing_accum["z"] = 0.0

    def finish_homing(self) -> None:
        """End manual homing mode and restore bounds checking."""
        self._homing_active = False

    # --- legacy set_z kept for convenience ---

    def set_z(self, z: float) -> None:
        self._client.set_kinematic_position(z=z)

    # --- motion ---

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, speed: float | None = None) -> None:
        """Relative move from current position. No clearance sequence."""
        if self._homing_active:
            # Pre-jog kinematic reset: shift the virtual coordinate frame so
            # the destination always lands at _HOMING_SAFE_MID.  This prevents
            # Klipper from rejecting moves that would stray below position_min
            # (e.g. after confirm_x_min sets X=0 and the user jogs further left).
            # SET_KINEMATIC_POSITION itself ignores position limits, so setting
            # to (SAFE_MID - delta) is always accepted; the subsequent G0 then
            # targets exactly SAFE_MID which is guaranteed in-range.
            resets = {}
            if dx != 0.0:
                resets["x"] = _HOMING_SAFE_MID - dx
                self._homing_accum["x"] += dx
            if dy != 0.0:
                resets["y"] = _HOMING_SAFE_MID - dy
                self._homing_accum["y"] += dy
            if dz != 0.0:
                resets["z"] = _HOMING_SAFE_MID - dz
                self._homing_accum["z"] += dz
            if resets:
                self._client.set_kinematic_position(**resets)
        else:
            if dx != 0.0 or dy != 0.0 or dz != 0.0:
                pos = self._client.get_position()
                self._check_bounds(
                    x=pos['x'] + dx if dx != 0.0 else None,
                    y=pos['y'] + dy if dy != 0.0 else None,
                    z=pos['z'] + dz if dz != 0.0 else None,
                )
        self._client.jog(dx, dy, dz, speed)

    def move_to(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None:
        """Move to a position (mm), applying toolhead offsets and checking bounds.

        Travel sequence: raise to clearance -> XY -> lower to Z.
        """
        offset_x = self._toolhead.offset_x if self._toolhead else 0.0
        offset_y = self._toolhead.offset_y if self._toolhead else 0.0

        target_x = x + offset_x if x is not None else None
        target_y = y + offset_y if y is not None else None

        self._check_bounds(x=target_x, y=target_y, z=z)
        self._check_bounds(z=self._clearance_z)

        self._client.move(z=self._clearance_z, speed=speed)
        self._client.move(x=target_x, y=target_y, speed=speed)
        self._client.move(z=z, speed=speed)

    def engage_tool(self, depth: float, speed: float | None = None) -> None:
        """Lower the tool by a specified depth (mm) from the current position."""
        pos = self.get_position()
        target_z = pos['z'] - depth
        self._check_bounds(z=target_z)
        self._client.move(z=target_z, speed=speed)

    def disengage_tool(self, depth: float, speed: float | None = None) -> None:
        """Raise the tool by a specified depth (mm) from the current position."""
        pos = self.get_position()
        target_z = pos['z'] + depth
        self._check_bounds(z=target_z)
        self._client.move(z=target_z, speed=speed)

    def get_position(self) -> dict[str, float]:
        return self._client.get_position()

    def get_state(self) -> str:
        return self._client.get_state()
