"""Orchestrator above MotionEngine, HomingManager, ToolheadManager, and WorkspaceManager."""

from rxn_bench_gantry.errors import (
    MotionLimitError,
    ToolheadNotMountedError,
    UnvalidatedGeometryError,
)
from rxn_bench_gantry.homing_manager import HomingManager
from rxn_bench_gantry.interfaces import MotionClientProtocol
from rxn_bench_gantry.motion_engine import MotionEngine
from rxn_bench_gantry.plate_geometry import PlateGeometry
from rxn_bench_gantry.toolhead_config import ToolheadGeometry
from rxn_bench_gantry.toolhead_manager import ToolheadManager
from rxn_bench_gantry.workspace_manager import WorkspaceManager


class GantryController:
    """High-level gantry controller - bounds-checked motion with toolhead geometry compensation."""

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
    ):
        """Initialise the controller and restore any persisted homing state.

        Args:
            client: Low-level motion client (MoonrakerClient or MockMoonrakerClient).
            clearance_z: Z height used as the safe travel altitude between moves, in mm.
            x_min: Left-side axis limit in mm.
            x_max: Right-side axis limit in mm.
            y_min: Front axis limit in mm.
            y_max: Back axis limit in mm.
            z_min: Lower Z limit in mm (Z=0 is the reference surface).
            z_max: Upper Z limit in mm.
        """
        self._toolhead_mgr = ToolheadManager()
        self._homing_mgr = HomingManager(
            client, clearance_z, x_min, x_max, y_min, y_max, z_min, z_max
        )
        self._engine = MotionEngine(client)
        self._workspace_mgr = WorkspaceManager()
        self._restore_state()

    def _restore_state(self) -> None:
        toolhead_name = self._homing_mgr.restore()
        if toolhead_name:
            try:
                self._toolhead_mgr.set_toolhead(toolhead_name)
            except Exception:
                pass

    @property
    def _safe_clearance_z(self) -> float:
        th = self._toolhead_mgr.toolhead
        tip_z = th.tip_offset_z if th else 0.0
        return max(self._homing_mgr.clearance_z, tip_z + self._homing_mgr.z_min)

    def _check_bounds(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        th = self._toolhead_mgr.toolhead
        h = self._homing_mgr
        half_fx = (th.footprint_x / 2) if th else 0.0
        half_fy = (th.footprint_y / 2) if th else 0.0
        tip_z = th.tip_offset_z if th else 0.0

        if x is not None:
            if x - half_fx < h.x_min or x + half_fx > h.x_max:
                raise MotionLimitError(
                    f"X={x:.1f} with footprint {half_fx*2:.1f}mm exceeds X limits "
                    f"[{h.x_min}, {h.x_max}]"
                )
        if y is not None:
            if y - half_fy < h.y_min or y + half_fy > h.y_max:
                raise MotionLimitError(
                    f"Y={y:.1f} with footprint {half_fy*2:.1f}mm exceeds Y limits "
                    f"[{h.y_min}, {h.y_max}]"
                )
        if z is not None:
            if z > h.z_max:
                raise MotionLimitError(f"Z={z:.1f} exceeds maximum {h.z_max}mm")
            if z - tip_z < h.z_min:
                raise MotionLimitError(
                    f"Z={z:.1f} would put tool tip at {z - tip_z:.1f}mm, "
                    f"below minimum {h.z_min}mm"
                )

    @property
    def has_saved_state(self) -> bool:
        return self._homing_mgr.has_saved_state

    @property
    def toolhead_mounted(self) -> bool:
        return self._toolhead_mgr.mounted

    def move_to(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None:
        """Move to an absolute position with safe clearance travel and toolhead offset compensation.

        Args:
            x: Target X coordinate in mm (workspace frame). None to skip X.
            y: Target Y coordinate in mm (workspace frame). None to skip Y.
            z: Target Z coordinate in mm. None to skip Z (stays at clearance height).
            speed: Travel speed in mm/min. Uses the client default if None.

        Raises:
            MotionLimitError: If the target position would exceed the calibrated axis limits.
        """
        th = self._toolhead_mgr.toolhead
        offset_x = (th.offset_x + th.tip_x) if th else 0.0
        offset_y = (th.offset_y + th.tip_y) if th else 0.0

        target_x = x + offset_x if x is not None else None
        target_y = y + offset_y if y is not None else None

        self._check_bounds(x=target_x, y=target_y, z=z)
        self._check_bounds(z=self._safe_clearance_z)

        self._engine.move_to(target_x, target_y, z, self._safe_clearance_z, speed)

    def jog(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        speed: float | None = None,
    ) -> None:
        """Relative move from the current position. Routes through the homing state machine when homing is active.

        Args:
            dx: X displacement in mm. Positive = right.
            dy: Y displacement in mm. Positive = forward.
            dz: Z displacement in mm. Positive = up.
            speed: Travel speed in mm/min. Uses the client default if None.

        Raises:
            MotionLimitError: If the resulting position would exceed the calibrated axis limits.
        """
        if self._homing_mgr.homing_active:
            self._homing_mgr.homing_jog_update(dx, dy, dz)
        else:
            if dx != 0.0 or dy != 0.0 or dz != 0.0:
                pos = self._engine.get_position()
                self._check_bounds(
                    x=pos["x"] + dx if dx != 0.0 else None,
                    y=pos["y"] + dy if dy != 0.0 else None,
                    z=pos["z"] + dz if dz != 0.0 else None,
                )
        self._engine.jog(dx, dy, dz, speed)

    def engage_tool(self, depth: float, speed: float | None = None) -> None:
        """Lower the tool tip by *depth* mm from the current Z.

        Args:
            depth: Distance in mm to descend.
            speed: Travel speed in mm/min. Uses the client default if None.

        Raises:
            MotionLimitError: If the target Z would fall below z_min.
        """
        pos = self._engine.get_position()
        target_z = pos["z"] - depth
        self._check_bounds(z=target_z)
        self._engine.move(z=target_z, speed=speed)

    def disengage_tool(self, depth: float, speed: float | None = None) -> None:
        """Raise the tool tip by *depth* mm from the current Z.

        Args:
            depth: Distance in mm to ascend.
            speed: Travel speed in mm/min. Uses the client default if None.

        Raises:
            MotionLimitError: If the target Z would exceed z_max.
        """
        pos = self._engine.get_position()
        target_z = pos["z"] + depth
        self._check_bounds(z=target_z)
        self._engine.move(z=target_z, speed=speed)

    def get_position(self) -> dict[str, float]:
        """Return the current XYZ position from the motion client."""
        return self._engine.get_position()

    def get_state(self) -> str:
        """Return the motion client's state string."""
        return self._engine.get_state()

    def save_and_park(self) -> None:
        """Move to the home corner, then persist calibrated limits for the next session."""
        h = self._homing_mgr
        try:
            self._engine.move(z=self._safe_clearance_z)
            self._engine.move(x=h.x_min, y=h.y_min)
        except Exception:
            pass
        h.save(toolhead_name=self._toolhead_mgr.name)

    def home_auto(self) -> None:
        """Home XY via Klipper G28 and set a safe kinematic Z reference."""
        self._homing_mgr.home_auto(self._safe_clearance_z)

    def start_manual_homing(self) -> None:
        """Begin manual limit calibration and invalidate any saved state."""
        self._homing_mgr.start_manual_homing()

    def confirm_x_min(self) -> None:
        """Declare the current X position as X=0 (left physical limit)."""
        self._homing_mgr.confirm_x_min()

    def confirm_x_max(self) -> None:
        """Record the current X travel distance as x_max."""
        self._homing_mgr.confirm_x_max()

    def confirm_y_min(self) -> None:
        """Declare the current Y position as Y=0 (front physical limit)."""
        self._homing_mgr.confirm_y_min()

    def confirm_y_max(self) -> None:
        """Record the current Y travel distance as y_max."""
        self._homing_mgr.confirm_y_max()

    def confirm_z_reference(self) -> None:
        """Declare the current Z position as Z=0 (working reference surface)."""
        self._homing_mgr.confirm_z_reference()

    def finish_homing(self) -> None:
        """End manual homing mode and re-enable bounds checking."""
        self._homing_mgr.finish_homing()

    def set_z(self, z: float) -> None:
        """Manually declare the current Z height without moving.

        Args:
            z: Height in mm to assign to the current carriage position.
        """
        self._homing_mgr.set_z(z)

    def get_toolhead(self) -> ToolheadGeometry | None:
        """Return the active toolhead geometry, or None if no toolhead is configured."""
        return self._toolhead_mgr.toolhead

    def get_toolhead_name(self) -> str:
        """Return the active toolhead's config name, or empty string if none."""
        return self._toolhead_mgr.name

    def get_toolhead_display_name(self) -> str:
        """Return the active toolhead's human-readable display name, or empty string if none."""
        return self._toolhead_mgr.display_name

    def set_toolhead(self, name: str) -> None:
        """Switch the active toolhead - a pure software change.

        With multiple heads mounted on the carriage at once, activation does
        not alter the physical configuration, so homing state and per-head
        mount confirmations are preserved. Scripts can switch between
        pre-confirmed heads unattended.

        Args:
            name: Toolhead name matching a config folder under ``toolheads/``.
        """
        self._toolhead_mgr.set_toolhead(name)

    def clear_toolhead(self) -> None:
        """Physically remove the active toolhead and revert to bare carriage geometry.

        Removing hardware changes the carriage envelope, so any saved homing
        state is invalidated if the removed head was confirmed mounted.
        """
        was_mounted = self._toolhead_mgr.mounted
        self._toolhead_mgr.clear_toolhead()
        if was_mounted:
            self._homing_mgr.invalidate_state()

    def set_toolhead_mounted(self, mounted: bool) -> None:
        """Record whether the active toolhead is physically installed.

        Mounting or unmounting hardware changes the carriage envelope, so any
        saved homing state is invalidated - but only when the state actually
        changes: re-confirming an already-mounted head (a script's
        mount_toolhead at startup) is a no-op and preserves homing.

        Args:
            mounted: True if the active toolhead is physically attached.
        """
        if self._toolhead_mgr.set_mounted(mounted):
            self._homing_mgr.invalidate_state()

    def get_mounted_toolheads(self) -> list[str]:
        """Return names of every toolhead confirmed as physically mounted."""
        return self._toolhead_mgr.mounted_toolheads

    def list_toolheads(self) -> list[tuple[str, str]]:
        """Return ``[(name, display_name), …]`` for every installed toolhead config."""
        return ToolheadManager.list_toolheads()

    def get_limits(self) -> str:
        """Return calibrated axis limits as a pipe-delimited string: ``x_min|x_max|y_min|y_max|z_min|z_max``."""
        h = self._homing_mgr
        return f"{h.x_min}|{h.x_max}|{h.y_min}|{h.y_max}|{h.z_min}|{h.z_max}"

    def set_workspace(self, name: str) -> None:
        """Load a workspace config by name from the bundled definitions directory.

        Args:
            name: Workspace name matching a file in ``workspace/definitions/``.
        """
        self._workspace_mgr.load(name)

    def load_workspace_from_yaml(self, content: str) -> None:
        """Load a workspace config from raw YAML content.

        Args:
            content: Full YAML string of a workspace definition.
        """
        self._workspace_mgr.load_from_yaml(content)

    def move_to_well(self, label: str, override_unvalidated: bool = False) -> None:
        """Move to a well by label using the active workspace.

        Using a toolhead for well work requires it to be confirmed: physically
        mounted (per-head confirmation, done once at setup) and with measured
        geometry. Bare-carriage well moves (no active toolhead) are allowed.

        Args:
            label: Well label, e.g. ``'A3'``, ``'H12'``, or ``'plate1/A3'``.
            override_unvalidated: If True, proceed even when the active toolhead's
                geometry is unvalidated (placeholder). Defaults to refusing.

        Raises:
            RuntimeError: If no workspace is loaded.
            KeyError: If the plate ID is not found in the current workspace.
            ValueError: If the well label format is invalid.
            MotionLimitError: If the resolved position exceeds axis limits.
            ToolheadNotMountedError: If the active toolhead has not been
                confirmed physically mounted.
            UnvalidatedGeometryError: If the active toolhead's geometry is
                unvalidated and override_unvalidated is False.
        """
        th = self._toolhead_mgr.toolhead
        if th is not None and not self._toolhead_mgr.mounted:
            raise ToolheadNotMountedError(
                f"Toolhead {self._toolhead_mgr.name!r} is not confirmed mounted. "
                "Confirm it once (ConfirmToolheadMounted / mount_toolhead) before "
                "well-targeted moves; the confirmation persists across switches."
            )
        if th is not None and not th.geometry_validated and not override_unvalidated:
            raise UnvalidatedGeometryError(
                f"Toolhead {self._toolhead_mgr.name!r} has unvalidated (placeholder) "
                "geometry. Well-targeted moves are refused until it is measured; "
                "pass override_unvalidated=True to proceed anyway."
            )
        x, y, _z = self._workspace_mgr.resolve_well(label)
        self.move_to(x=x, y=y)

    def list_workspaces(self) -> list[str]:
        """Return names of all available workspace definition files."""
        return WorkspaceManager.list_available()

    def get_workspace_name(self) -> str:
        """Return the name of the currently loaded workspace, or empty string if none."""
        return self._workspace_mgr.name

    def get_workspace_yaml(self) -> str:
        """Return the active workspace as a YAML string, or empty string if none is loaded.

        The workspace manager is the single source of truth, so this reflects
        workspaces loaded by name, from raw YAML, or restored from disk at startup.
        """
        return self._workspace_mgr.to_yaml()

    def get_labware_yaml(self) -> str:
        """Return every bundled labware (plate geometry) definition as one YAML document."""
        return PlateGeometry.dump_all_yaml()
