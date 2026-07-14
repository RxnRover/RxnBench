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

    # Safe raise height for a bare carriage (or a toolhead shallow enough not
    # to need more). Not machine-configurable: it is not a physical fact about
    # the machine like the axis limits are, just a comfortable travel height,
    # and every Z move is bounds-checked against z_min/tip_offset_z regardless
    # of this value, so getting it "wrong" costs a rejected move, not a crash.
    _BARE_CLEARANCE_Z_MM = 50.0

    def __init__(
        self,
        client: MotionClientProtocol,
        x_min: float = 0.0,
        x_max: float = 350.0,
        y_min: float = 0.0,
        y_max: float = 350.0,
        z_min: float = 0.0,
        z_max: float = 340.0,
        z_clearance_padding_mm: float = 5.0,
        crossbar_clearance_above_tip_mm: float | None = None,
        crossbar_y_thickness_mm: float | None = None,
    ):
        """Initialise the controller and restore any persisted homing state.

        Args:
            client: Low-level motion client (MoonrakerClient or MockMoonrakerClient).
            x_min: Left-side axis limit in mm.
            x_max: Right-side axis limit in mm.
            y_min: Front axis limit in mm.
            y_max: Back axis limit in mm.
            z_min: Lower Z limit in mm (Z=0 is the reference surface).
            z_max: Upper Z limit in mm.
            z_clearance_padding_mm: Safety margin added above the tallest
                loaded labware when computing safe clearance-travel height.
            crossbar_clearance_above_tip_mm: Height of the X-gantry crossbar's
                underside above the tip (see MachineConfig). None disables the
                crossbar collision check.
            crossbar_y_thickness_mm: The crossbar's Y extent. None disables the
                crossbar collision check.
        """
        self._toolhead_mgr = ToolheadManager()
        self._homing_mgr = HomingManager(client, x_min, x_max, y_min, y_max, z_min, z_max)
        self._engine = MotionEngine(client)
        self._workspace_mgr = WorkspaceManager()
        self._z_clearance_padding_mm = z_clearance_padding_mm
        self._crossbar_clearance_above_tip_mm = crossbar_clearance_above_tip_mm
        self._crossbar_y_thickness_mm = crossbar_y_thickness_mm
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
        """Height to raise to during clearance travel: enough to clear every
        loaded plate's top surface as well as the active tip.

        Derived, not a single fixed guess: the bare-carriage floor, the
        active tip's own hang-down, and (if a workspace is loaded) the
        tallest placed plate's top surface plus a configurable safety
        padding all compete, and clearance travel rises to whichever demands
        the most headroom. This replaces a flat constant that had no idea
        whether a tall beaker was sharing the deck with a low-profile plate,
        so travel over an unexpectedly tall container was never actually
        checked against real geometry. Every Z target is still bounds-checked
        against z_min/z_max/tip_offset_z regardless of this value.
        """
        th = self._toolhead_mgr.toolhead
        tip_z = th.tip_offset_z if th else 0.0
        labware_top = self._workspace_mgr.max_labware_top_z()
        labware_clearance = labware_top + self._z_clearance_padding_mm if labware_top > 0 else 0.0
        return max(
            self._BARE_CLEARANCE_Z_MM,
            tip_z + self._homing_mgr.z_min,
            labware_clearance,
        )

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
        # Plain move: no plate context, so clear everything on the deck.
        self._travel_to(x, y, z, self._safe_clearance_z, speed)

    def _travel_to(
        self,
        x: float | None,
        y: float | None,
        z: float | None,
        clearance_z: float,
        speed: float | None = None,
    ) -> None:
        """Offset-compensated safe-travel move at an explicit clearance height.

        Shared by move_to (full-deck clearance) and move_to_well (which may pass
        a lower intra-plate clearance). Applies the active toolhead's XY offset,
        bounds-checks both the target and the clearance height, then hands the
        raise->XY->lower sequence to the engine.
        """
        th = self._toolhead_mgr.toolhead
        offset_x = (th.offset_x + th.tip_x) if th else 0.0
        offset_y = (th.offset_y + th.tip_y) if th else 0.0

        target_x = x + offset_x if x is not None else None
        target_y = y + offset_y if y is not None else None

        self._check_bounds(x=target_x, y=target_y, z=z)
        self._check_bounds(z=clearance_z)

        self._engine.move_to(target_x, target_y, z, clearance_z, speed)

    def _plate_clearance_z(self, plate_id: str) -> float:
        """Travel height that just clears ONE plate - for intra-plate well moves.

        When both the start and end wells are in the same plate, only that
        plate's own (uniform) top surface has to be cleared, not the tallest
        plate anywhere on the deck - so the tip rises just `padding` above this
        plate's rim instead of all the way to the full deck clearance, saving
        the raise/lower time between wells. Still keeps the tip above z_min.
        Deliberately omits the bare-carriage comfort floor (_BARE_CLEARANCE_Z_MM):
        staying low over a known short plate is the entire point.
        """
        th = self._toolhead_mgr.toolhead
        tip_z = th.tip_offset_z if th else 0.0
        plate_top = self._workspace_mgr.plate_top_z(plate_id)
        return max(tip_z + self._homing_mgr.z_min, plate_top + self._z_clearance_padding_mm)

    def _clearance_for_well_target(self, plate_id: str) -> float:
        """Pick intra-plate clearance if the carriage is already over this plate.

        Same-plate is decided from the *actual current tip position* vs. the
        target plate's footprint (stateless and exact for the supported 0/90
        orientations, which keep the plate rectangle axis-aligned), so it can't
        be fooled by stale tracking after a manual jog or a cross-plate hop. Any
        failure to determine position falls back to the full, safe deck clearance.
        """
        try:
            pos = self._engine.get_position()
            x_min, x_max, y_min, y_max = self._workspace_mgr.plate_footprint_bounds(plate_id)
        except Exception:
            return self._safe_clearance_z
        th = self._toolhead_mgr.toolhead
        off_x = (th.offset_x + th.tip_x) if th else 0.0
        off_y = (th.offset_y + th.tip_y) if th else 0.0
        tip_x = pos["x"] - off_x   # where the tip is, not the carriage
        tip_y = pos["y"] - off_y
        over_plate = (x_min <= tip_x <= x_max) and (y_min <= tip_y <= y_max)
        return self._plate_clearance_z(plate_id) if over_plate else self._safe_clearance_z

    def _crossbar_min_command_z(self, carriage_y: float) -> float | None:
        """Lowest Z command allowed at a carriage Y by the X-gantry crossbar.

        The crossbar spans X at the carriage's Y and sits `H` above the tip, so
        to keep the bar clear of a plate whose top is at `plate_top` the tip
        (= the Z command, in the workspace Z frame) must stay at or above
        `plate_top - H`. Returns the tightest such bound over every plate sharing
        the crossbar's Y band, or None when the check is disabled (crossbar
        geometry not configured) or nothing shares the band.
        """
        h = self._crossbar_clearance_above_tip_mm
        t = self._crossbar_y_thickness_mm
        if h is None or t is None:
            return None
        top = self._workspace_mgr.max_top_in_y_band(carriage_y - t / 2, carriage_y + t / 2)
        return (top - h) if top is not None else None

    def jog(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        speed: float | None = None,
    ) -> None:
        """Relative move from the current position. Bounds checking is skipped while homing is active.

        Args:
            dx: X displacement in mm. Positive = right.
            dy: Y displacement in mm. Positive = forward.
            dz: Z displacement in mm. Positive = up.
            speed: Travel speed in mm/min. Uses the client default if None.

        Raises:
            MotionLimitError: If the resulting position would exceed the calibrated axis limits.
        """
        if not self._homing_mgr.homing_active:
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
        # Descending lowers the crossbar too; refuse if it would hit a taller
        # plate sharing the current Y-row.
        crossbar_min = self._crossbar_min_command_z(pos["y"])
        if crossbar_min is not None and target_z < crossbar_min:
            raise MotionLimitError(
                f"X-gantry crossbar would collide with a taller plate in this "
                f"Y-row: engaging to Z={target_z:.1f}mm needs the tip at/above "
                f"Z={crossbar_min:.1f}mm to keep the bar clear."
            )
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
        """Declare the current X position as X=0 (left physical limit). Use whichever X corner you're at."""
        self._homing_mgr.confirm_x_min()

    def confirm_x_max(self) -> None:
        """Declare the current X position as the fixed x_max (right physical limit)."""
        self._homing_mgr.confirm_x_max()

    def confirm_y_min(self) -> None:
        """Declare the current Y position as Y=0 (front physical limit). Use whichever Y corner you're at."""
        self._homing_mgr.confirm_y_min()

    def confirm_y_max(self) -> None:
        """Declare the current Y position as the fixed y_max (back physical limit)."""
        self._homing_mgr.confirm_y_max()

    def confirm_z_reference(self) -> None:
        """Declare the current Z position as Z=0 (working reference surface)."""
        self._homing_mgr.confirm_z_reference()

    def finish_homing(self) -> None:
        """End manual homing mode, re-enable bounds checking, and persist the result.

        Saves immediately (rather than waiting for the next SaveAndPark) so the
        UI's homed indicator reflects reality as soon as the operator finishes
        the wizard, instead of silently staying "Not homed" until some later,
        unrelated command happens to save.
        """
        self._homing_mgr.finish_homing()
        self._homing_mgr.save(toolhead_name=self._toolhead_mgr.name)

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

    def calibrate_toolhead_tip(self, measured_x: float, measured_y: float, wells: str) -> dict[str, float]:
        """Derive and persist the active toolhead's tip offset from measured well centre(s).

        The operator jogs the physical tip to the centre of one or more
        calibration wells and reports the *averaged* resulting machine
        coordinates here; ``wells`` names every well that went into that
        average (pipe-delimited ``plate_id/well_label`` entries). The offset
        is back-solved against the average of those wells' nominal positions,
        so it is independent of where the wells sit on the deck. Averaging
        several of a plate's corner wells (instead of just one) also cancels
        out per-well measurement noise and catches gross rotation/placement
        errors that a single well can't reveal.

        Args:
            measured_x: Average machine X across the measured well centres.
            measured_y: Average machine Y across the measured well centres.
            wells: Pipe-delimited ``plate_id/well_label`` entries, e.g.
                ``'96-well/H1|96-well/H12|96-well/A1|96-well/A12'``.

        Returns:
            Dict with the averaged nominal well position and the resulting
            tip_x/tip_y - logged verbatim by the caller, and returned to the
            operator so the calibration dialog can show exactly what was
            measured and saved instead of leaving it opaque.

        Raises:
            RuntimeError: If no toolhead is active or no wells were given.
        """
        th = self._toolhead_mgr.toolhead
        if th is None:
            raise RuntimeError("No active toolhead to calibrate.")
        well_labels = [w.strip() for w in wells.split("|") if w.strip()]
        if not well_labels:
            raise RuntimeError("calibrate_toolhead_tip requires at least one well.")
        nominals = [self._workspace_mgr.resolve_well(label) for label in well_labels]
        nominal_x = sum(n[0] for n in nominals) / len(nominals)
        nominal_y = sum(n[1] for n in nominals) / len(nominals)
        tip_x = measured_x - nominal_x - th.offset_x
        tip_y = measured_y - nominal_y - th.offset_y
        self._toolhead_mgr.set_tip_offset(tip_x, tip_y)
        return {"nominal_x": nominal_x, "nominal_y": nominal_y, "tip_x": tip_x, "tip_y": tip_y}

    def calibrate_toolhead_tip_z(self, measured_z: float) -> None:
        """Derive and persist the active toolhead's Z offset from a measured surface touch.

        The operator lowers the tip until it touches the deck/reference
        surface (Z=0) and reports the resulting carriage Z here. Since the tip
        is physically at Z=0 at that instant, the carriage's Z reading at that
        moment *is* the toolhead's tip_offset_z - no well lookup needed.

        Args:
            measured_z: Carriage Z position in mm when the tip touches the Z=0 reference surface.

        Raises:
            RuntimeError: If no toolhead is active.
        """
        if self._toolhead_mgr.toolhead is None:
            raise RuntimeError("No active toolhead to calibrate.")
        self._toolhead_mgr.set_tip_offset_z(measured_z)

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

    def get_safe_clearance_z(self) -> float:
        """Return the current safe clearance-travel height in mm.

        Exposed so frontend visualizations (e.g. the X/Z and Y/Z side views)
        can show the real, currently-computed value instead of an
        independently-maintained copy of this formula - which would risk
        drifting from the actual value every motion command already uses.
        """
        return self._safe_clearance_z

    def get_limits(self) -> str:
        """Return calibrated axis limits + safe clearance + crossbar geometry as a
        pipe-delimited string:
        ``x_min|x_max|y_min|y_max|z_min|z_max|safe_clearance_z|crossbar_clearance_above_tip|crossbar_y_thickness``.

        The two trailing crossbar fields are empty strings when the crossbar
        model is not configured (so the frontend draws nothing). Kept as one
        SString blob - appending fields is wire-compatible and needs no proto
        change; the frontend parses 7 or 9 fields.
        """
        h = self._homing_mgr

        def _f(v: float | None) -> str:
            return "" if v is None else str(v)

        return (
            f"{h.x_min}|{h.x_max}|{h.y_min}|{h.y_max}|{h.z_min}|{h.z_max}|"
            f"{self._safe_clearance_z}|"
            f"{_f(self._crossbar_clearance_above_tip_mm)}|{_f(self._crossbar_y_thickness_mm)}"
        )

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

    def move_to_well(self, label: str, override_unvalidated: bool = False) -> dict[str, float]:
        """Move to a well by label using the active workspace.

        Using a toolhead for well work requires it to be confirmed: physically
        mounted (per-head confirmation, done once at setup) and with measured
        geometry. Bare-carriage well moves (no active toolhead) are allowed.

        Args:
            label: Well label, e.g. ``'A3'``, ``'H12'``, or ``'plate1/A3'``.
            override_unvalidated: If True, proceed even when the active toolhead's
                geometry is unvalidated (placeholder), and skip the engagement-depth
                safety check below. Defaults to refusing. Also used by the toolhead
                calibration wizard, which visits corner wells purely to position the
                tip - it never calls engage_tool - so a toolhead's configured
                z_engage exceeding that well's depth is not actually a collision risk
                there, only for the normal move_to_well-then-engage_tool workflow.

        Returns:
            Dict with the well's expected (nominal, pre-toolhead-offset)
            position and the gantry's actual position once the move
            completes - logged verbatim by the caller so a mismatch between
            hand-computed geometry and real hardware behaviour is visible in
            the session log for every well move, not just during calibration.

        Raises:
            RuntimeError: If no workspace is loaded.
            KeyError: If the plate ID is not found in the current workspace.
            ValueError: If the well label format is invalid.
            MotionLimitError: If the resolved position exceeds axis limits,
                or (when override_unvalidated is False) the active toolhead's
                engagement depth (z_engage) exceeds this well's depth and
                would collide with its bottom.
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
        # z is the well's *opening* (plate top surface), not its bottom - see
        # resolve_well. Docking there (instead of leaving Z at whatever the
        # travel clearance height happened to be) is what makes engage_tool's
        # z_engage a physically meaningful descent into the well, regardless
        # of how tall the clearance height needed to be for other labware
        # sharing the deck.
        x, y, z = self._workspace_mgr.resolve_well(label)
        if th is not None and not override_unvalidated:
            well_depth = self._workspace_mgr.get_well_depth(label)
            if th.z_engage > well_depth:
                raise MotionLimitError(
                    f"Toolhead {self._toolhead_mgr.name!r}'s engagement depth "
                    f"(z_engage={th.z_engage:.1f}mm) exceeds well {label!r}'s "
                    f"depth ({well_depth:.1f}mm) - would collide with the well bottom."
                )
        # Only clear the whole deck when hopping to a different plate; when the
        # carriage is already over this plate, travel at just this plate's own
        # clearance height (uniform top) to skip the wasteful full raise/lower.
        plate_id = self._workspace_mgr.plate_id_for_label(label)
        clearance = self._clearance_for_well_target(plate_id)
        # X-gantry crossbar: refuse if docking at this well would drive the bar
        # into a taller plate sharing the target's Y-row; otherwise raise the
        # travel clearance so the bar clears that plate on the way in.
        off_y = (th.offset_y + th.tip_y) if th else 0.0
        crossbar_min = self._crossbar_min_command_z(y + off_y)
        if crossbar_min is not None:
            if z < crossbar_min:
                raise MotionLimitError(
                    f"X-gantry crossbar would collide with a taller plate sharing "
                    f"well {label!r}'s Y-row: docking at Z={z:.1f}mm needs the tip "
                    f"at/above Z={crossbar_min:.1f}mm to keep the bar clear."
                )
            clearance = max(clearance, crossbar_min)
        self._travel_to(x, y, z, clearance)
        actual = self._engine.get_position()
        return {
            "expected_well_x": x,
            "expected_well_y": y,
            "expected_well_z": z,
            "actual_x": actual["x"],
            "actual_y": actual["y"],
            "actual_z": actual["z"],
        }

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
