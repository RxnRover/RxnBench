"""Axis-limit calibration and homing state machine."""
from rxn_bench_gantry.homing_state import (
    save as _save_state,
    load as _load_state,
    invalidate as _invalidate_state,
)
from rxn_bench_gantry.interfaces import MotionClientProtocol

_HOMING_SAFE_MID = 175.0


class HomingManager:
    """Tracks calibrated axis limits and owns the manual/auto homing state machine."""

    def __init__(
        self,
        client: MotionClientProtocol,
        x_min: float = 0.0,
        x_max: float = 350.0,
        y_min: float = 0.0,
        y_max: float = 350.0,
        z_min: float = 0.0,
        z_max: float = 340.0,
    ) -> None:
        """Initialise with the machine's fixed axis limits; call :meth:`restore` for the origin.

        x_min/x_max/y_min/y_max are the machine's known, fixed bed size -
        manual homing only ever re-establishes where the carriage currently
        is relative to that fixed frame, since there are no X/Y endstops to
        trust; the bed's physical extent doesn't change between sessions and
        is never re-measured. The operator can start from *any* of the 4
        corners each session (confirm_x_min or confirm_x_max, confirm_y_min
        or confirm_y_max - whichever matches where they happen to be) rather
        than a fixed per-machine assumption, so only one X confirm and one Y
        confirm are ever needed regardless of which corner is convenient.

        Args:
            client: Low-level motion client used during auto-homing and kinematic resets.
            x_min: Left axis limit in mm.
            x_max: Right axis limit in mm (fixed bed width).
            y_min: Front axis limit in mm.
            y_max: Back axis limit in mm (fixed bed height).
            z_min: Lower Z limit in mm.
            z_max: Upper Z limit in mm.
        """
        self._client = client
        self._x_min = x_min
        self._x_max = x_max
        self._y_min = y_min
        self._y_max = y_max
        self._z_min = z_min
        self._z_max = z_max
        self._homing_active: bool = False
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
        """Begin manual limit calibration and invalidate saved state.

        Declares the current (physically arbitrary) position as the firmware's
        safe mid-point exactly once, so Klipper accepts jogs in either
        direction before either corner is known. Nothing re-declares position
        after this: every subsequent jog is a single real relative move, and
        the firmware's own tracked position is trusted from here on - it is
        never faked again, so the displayed position stays accurate throughout
        calibration and each jog click costs one motion command instead of two.
        """
        _invalidate_state()
        self._has_saved_state = False
        self._homing_active = True
        self._client.set_kinematic_position(
            x=_HOMING_SAFE_MID, y=_HOMING_SAFE_MID, z=_HOMING_SAFE_MID
        )

    def confirm_x_min(self) -> None:
        """Declare the current real X position as X=0 (left physical limit).

        x_max is never re-measured here: the bed's physical width is a fixed
        machine constant, so only where the carriage currently sits relative
        to it needs re-establishing each session. Use this (instead of
        confirm_x_max) when you're physically at the left edge; either one
        alone is sufficient to fix the X axis for this session.
        """
        self._client.set_kinematic_position(x=self._x_min)

    def confirm_x_max(self) -> None:
        """Declare the current real X position as X=x_max (right physical limit).

        Same idea as confirm_x_min, mirrored: use this when it's more
        convenient to start from the right edge instead. Only one of the two
        needs to be clicked per session, whichever corner you're actually at.
        """
        self._client.set_kinematic_position(x=self._x_max)

    def confirm_y_min(self) -> None:
        """Declare the current real Y position as Y=0 (front physical limit).

        y_max is never re-measured here, for the same reason as x_max above.
        Use this when you're physically at the front edge.
        """
        self._client.set_kinematic_position(y=self._y_min)

    def confirm_y_max(self) -> None:
        """Declare the current real Y position as Y=y_max (back physical limit).

        Mirrors confirm_y_min - use whichever matches where you are.
        """
        self._client.set_kinematic_position(y=self._y_max)

    def confirm_z_reference(self) -> None:
        """Declare the current Z position as Z=0 (working reference surface)."""
        self._client.set_kinematic_position(z=0)

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
        self._has_saved_state = True
        self._is_calibrated = False
        return state.get("toolhead_name", "")

    def invalidate_state(self) -> None:
        """Mark the persisted homing state as dirty and clear the in-memory calibration flag."""
        _invalidate_state()
        self._has_saved_state = False
        self._is_calibrated = False
