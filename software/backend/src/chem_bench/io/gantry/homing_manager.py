"""
Axis-limit management and manual/auto homing state machine.

Owns calibrated axis limits, the homing accumulator, the kinematic-reset
jog trick, and JSON persistence via homing_state.py.  Independent of
toolhead logic — the controller passes clearance_z and toolhead_name as
plain values when needed.

Author: John Brittain
Date: Jun 2026
"""
from .homing_state import (
    save as _save_state,
    load as _load_state,
    invalidate as _invalidate_state,
)
from chem_bench.io.interfaces.motion import MotionClientProtocol
from chem_bench.io.errors import MotionLimitError

# Pre-jog kinematic reset target during manual homing.  Must be within any
# reasonable Klipper position_max while still allowing ±100 mm steps.
_HOMING_SAFE_MID = 175.0


class HomingManager:

    def __init__(
        self,
        client: MotionClientProtocol,
        clearance_z: float = 50.0,
        x_min: float = 0.0,
        x_max: float = 350.0,
        y_min: float = 0.0,
        y_max: float = 350.0,
        z_min: float = 0.0,
        z_max: float = 340.0,
    ) -> None:
        self._client = client
        self._clearance_z = clearance_z
        self._x_min = x_min
        self._x_max = x_max
        self._y_min = y_min
        self._y_max = y_max
        self._z_min = z_min
        self._z_max = z_max
        self._homing_active: bool = False
        self._homing_accum: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._has_saved_state: bool = False
        # True only after a fresh homing procedure in this session (auto or manual).
        # Restored-from-disk state starts as False so save() is blocked until the
        # operator re-verifies limits — prevents overwriting valid calibration with
        # unconfirmed state when the machine has been moved while powered off.
        self._is_calibrated: bool = False

    # --- properties read by the controller ---

    @property
    def x_min(self) -> float:
        return self._x_min

    @property
    def x_max(self) -> float:
        return self._x_max

    @property
    def y_min(self) -> float:
        return self._y_min

    @property
    def y_max(self) -> float:
        return self._y_max

    @property
    def z_min(self) -> float:
        return self._z_min

    @property
    def z_max(self) -> float:
        return self._z_max

    @property
    def clearance_z(self) -> float:
        return self._clearance_z

    @property
    def homing_active(self) -> bool:
        return self._homing_active

    @property
    def has_saved_state(self) -> bool:
        return self._has_saved_state

    # --- homing ---

    def home_auto(self, safe_clearance_z: float) -> None:
        """Home XY via endstops.

        safe_clearance_z is computed by the controller (max of clearance_z and
        tip_offset_z + z_min) and passed in so this method stays toolhead-agnostic.
        """
        if "z" in self._client.get_homed_axes().lower():
            self._client.move(z=safe_clearance_z)
        self._client.home("XY")
        self._client.set_kinematic_position(z=_HOMING_SAFE_MID)
        self._is_calibrated = True

    def start_manual_homing(self) -> None:
        """Begin manual homing with a toolhead mounted.

        Kinematic position is set to _HOMING_SAFE_MID on all axes so subsequent
        jogs always have room in both directions.  Bounds checking is suspended
        in GantryController until finish_homing() is called.
        """
        _invalidate_state()
        self._has_saved_state = False
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
        travel = abs(self._homing_accum["x"])
        if travel < 1.0:
            raise MotionLimitError(
                "Confirm X+ requires at least 1 mm of travel from X− first. "
                "Jog to the X+ physical limit before confirming."
            )
        self._x_max = travel
        self._homing_accum["x"] = 0.0

    def confirm_y_min(self) -> None:
        """Declare the current Y position as Y=0 and store it as the Y minimum."""
        self._client.set_kinematic_position(y=_HOMING_SAFE_MID)
        self._y_min = 0.0
        self._homing_accum["y"] = 0.0

    def confirm_y_max(self) -> None:
        """Record the accumulated Y travel from Y_min as the Y maximum."""
        travel = abs(self._homing_accum["y"])
        if travel < 1.0:
            raise MotionLimitError(
                "Confirm Y+ requires at least 1 mm of travel from Y− first. "
                "Jog to the Y+ physical limit before confirming."
            )
        self._y_max = travel
        self._homing_accum["y"] = 0.0

    def confirm_z_reference(self) -> None:
        """Declare the current Z position as Z=0."""
        self._client.set_kinematic_position(z=0)
        self._homing_accum["z"] = 0.0

    def finish_homing(self) -> None:
        """End manual homing mode and restore bounds checking."""
        self._homing_active = False
        self._is_calibrated = True

    def set_z(self, z: float) -> None:
        self._client.set_kinematic_position(z=z)

    def homing_jog_update(self, dx: float, dy: float, dz: float) -> None:
        """Apply the kinematic-reset trick for a single manual-homing jog step.

        Shifts the virtual coordinate frame so the jog destination always lands
        at _HOMING_SAFE_MID, preventing Klipper from rejecting moves that stray
        below position_min after confirm_x_min sets X=0.  The actual G0 move is
        issued separately by MotionEngine.jog().
        """
        resets: dict[str, float] = {}
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

    # --- persistence ---

    def save(self, toolhead_name: str) -> None:
        """Persist calibrated limits.  toolhead_name is a plain str from the controller.

        Raises RuntimeError if limits have not been freshly calibrated in this session.
        This prevents overwriting a valid on-disk calibration with unverified state
        (e.g. auto-restored limits that were never re-confirmed after a power-off move).
        """
        if not self._is_calibrated:
            raise RuntimeError(
                "Cannot save homing state: axis limits have not been calibrated in "
                "this session. Run HomeAuto or complete manual homing first."
            )
        _save_state(
            x_min=self._x_min,
            x_max=self._x_max,
            y_min=self._y_min,
            y_max=self._y_max,
            clearance_z=self._clearance_z,
            toolhead_name=toolhead_name,
            is_calibrated=True,
        )
        self._has_saved_state = True

    def restore(self) -> str:
        """Load saved state and apply axis limits.

        Returns the saved toolhead name (or '') for the controller to pass to
        ToolheadManager.  HomingManager does not import ToolheadManager.
        """
        state = _load_state()
        if state is None:
            return ""
        self._x_min = state.get("x_min", self._x_min)
        self._x_max = state.get("x_max", self._x_max)
        self._y_min = state.get("y_min", self._y_min)
        self._y_max = state.get("y_max", self._y_max)
        self._clearance_z = state.get("clearance_z", self._clearance_z)
        self._has_saved_state = True
        self._is_calibrated = False  # restored from disk; operator must re-home to allow save
        return state.get("toolhead_name", "")

    def invalidate_state(self) -> None:
        _invalidate_state()
        self._has_saved_state = False
        self._is_calibrated = False
