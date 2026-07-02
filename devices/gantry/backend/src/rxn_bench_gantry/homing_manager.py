"""Axis-limit calibration and homing state machine."""
from rxn_bench_gantry.homing_state import (
    save as _save_state,
    load as _load_state,
    invalidate as _invalidate_state,
)
from rxn_bench_gantry.interfaces import MotionClientProtocol
from rxn_bench_gantry.errors import MotionLimitError

_HOMING_SAFE_MID = 175.0


class HomingManager:
    """Tracks calibrated axis limits and owns the manual/auto homing state machine."""

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
        """Initialise with default axis limits; call :meth:`restore` to load persisted values.

        Args:
            client: Low-level motion client used during auto-homing and kinematic resets.
            clearance_z: Default safe travel altitude in mm.
            x_min: Initial left axis limit in mm.
            x_max: Initial right axis limit in mm.
            y_min: Initial front axis limit in mm.
            y_max: Initial back axis limit in mm.
            z_min: Initial lower Z limit in mm.
            z_max: Initial upper Z limit in mm.
        """
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
        self._is_calibrated: bool = False

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

    def home_auto(self, safe_clearance_z: float) -> None:
        """Home XY via Klipper G28 and assign a safe kinematic Z mid-point.

        Args:
            safe_clearance_z: Z height to raise to before homing, if Z is already homed.
        """
        if "z" in self._client.get_homed_axes().lower():
            self._client.move(z=safe_clearance_z)
        self._client.home("XY")
        self._client.set_kinematic_position(z=_HOMING_SAFE_MID)
        self._is_calibrated = True

    def start_manual_homing(self) -> None:
        """Begin manual limit calibration, invalidate saved state, and reset jog accumulators."""
        _invalidate_state()
        self._has_saved_state = False
        self._homing_active = True
        self._homing_accum = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._client.set_kinematic_position(
            x=_HOMING_SAFE_MID, y=_HOMING_SAFE_MID, z=_HOMING_SAFE_MID
        )

    def confirm_x_min(self) -> None:
        """Declare the current X position as X=0 and reset the X accumulator."""
        self._client.set_kinematic_position(x=_HOMING_SAFE_MID)
        self._x_min = 0.0
        self._homing_accum["x"] = 0.0

    def confirm_x_max(self) -> None:
        """Record accumulated X travel as x_max.

        Raises:
            MotionLimitError: If less than 1 mm of X travel has been accumulated.
        """
        travel = abs(self._homing_accum["x"])
        if travel < 1.0:
            raise MotionLimitError(
                "Confirm X+ requires at least 1 mm of travel from X− first."
            )
        self._x_max = travel
        self._homing_accum["x"] = 0.0

    def confirm_y_min(self) -> None:
        """Declare the current Y position as Y=0 and reset the Y accumulator."""
        self._client.set_kinematic_position(y=_HOMING_SAFE_MID)
        self._y_min = 0.0
        self._homing_accum["y"] = 0.0

    def confirm_y_max(self) -> None:
        """Record accumulated Y travel as y_max.

        Raises:
            MotionLimitError: If less than 1 mm of Y travel has been accumulated.
        """
        travel = abs(self._homing_accum["y"])
        if travel < 1.0:
            raise MotionLimitError(
                "Confirm Y+ requires at least 1 mm of travel from Y− first."
            )
        self._y_max = travel
        self._homing_accum["y"] = 0.0

    def confirm_z_reference(self) -> None:
        """Declare the current Z position as Z=0 (working reference surface)."""
        self._client.set_kinematic_position(z=0)
        self._homing_accum["z"] = 0.0

    def finish_homing(self) -> None:
        """End manual homing mode and mark the machine as calibrated."""
        self._homing_active = False
        self._is_calibrated = True

    def set_z(self, z: float) -> None:
        """Manually declare the current Z height without moving.

        Args:
            z: Height in mm to assign to the current carriage position.
        """
        self._client.set_kinematic_position(z=z)

    def homing_jog_update(self, dx: float, dy: float, dz: float) -> None:
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

    def save(self, toolhead_name: str) -> None:
        """Persist the current calibrated limits to disk.

        Args:
            toolhead_name: Name of the currently active toolhead to store alongside the limits.

        Raises:
            RuntimeError: If the machine has not been calibrated in this session.
        """
        if not self._is_calibrated:
            raise RuntimeError(
                "Cannot save homing state: axis limits have not been calibrated in "
                "this session. Complete manual homing first."
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
        """Load persisted axis limits from disk and return the stored toolhead name.

        Returns:
            The toolhead name from the saved state, or empty string if no valid state exists.
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
        self._is_calibrated = False
        return state.get("toolhead_name", "")

    def invalidate_state(self) -> None:
        """Mark the persisted homing state as dirty and clear the in-memory calibration flag."""
        _invalidate_state()
        self._has_saved_state = False
        self._is_calibrated = False
