"""SiLA2 feature for the Gantry."""
import asyncio
import dataclasses
import uuid

from unitelabs.cdk import sila

from rxn_bench_gantry.errors import ExperimentLockError
from rxn_bench_gantry.interfaces import GantryControllerProtocol
from rxn_bench_gantry.session_log import SessionLog


@dataclasses.dataclass
class Position:
    """XYZ position of the gantry in mm."""
    x: float
    y: float
    z: float


@dataclasses.dataclass
class ToolheadInfo:
    """Current toolhead geometry streamed as an ObservableProperty."""
    active: bool
    name: str
    display_name: str
    footprint_x: float
    footprint_y: float
    offset_x: float
    offset_y: float
    tip_offset_z: float
    z_engage: float
    tip_x: float = 0.0
    tip_y: float = 0.0
    toolhead_mounted: bool = False
    # Pipe-delimited names of every head confirmed mounted (mount state is
    # per-head and survives activation switches).
    mounted_toolheads: str = ""
    calibrated_at: str = ""  # ISO timestamp of the last calibration wizard run, "" if never


class Gantry(sila.Feature):
    """SiLA2 Gantry feature. Exposes gantry motion as gRPC commands and observable properties."""

    def __init__(self, controller: GantryControllerProtocol):
        super().__init__(
            originator="edu.iastate.ames",
            category="rxnbench",
            version="0.1",
            maturity_level="Draft",
        )
        self._controller = controller
        self._hw_lock = asyncio.Lock()
        self._current_well:     str = ""
        self._current_action:   str = "Standby"
        self._experiment_state: str = "idle"   # idle | running | paused | stop_requested
        self._experiment_token: str = ""       # secret held by the lock-owning script
        self._log = SessionLog(prefix="gantry")

    async def _run(self, fn, *args, log: str = "", **log_kw):
        """Acquire the hardware lock, run fn(*args) in a thread, and log the result.

        If fn returns a dict (e.g. move_to_well's expected-vs-actual position),
        its keys are merged into the log entry alongside log_kw, so per-call
        diagnostic detail can be added without changing this helper's callers.
        """
        async with self._hw_lock:
            try:
                result = await asyncio.to_thread(fn, *args)
                if log:
                    extra = result if isinstance(result, dict) else {}
                    self._log.log(log, ok=True, **log_kw, **extra)
                return result
            except Exception as exc:
                if log:
                    self._log.log(log, ok=False, error=str(exc), **log_kw)
                raise

    def _check_lock(self, token: str = "") -> None:
        """Reject a command while a script holds the experiment lock.

        Commands issued with the lock holder's token pass through; everything
        else (manual UI actions, other clients) is rejected until the lock is
        released. Called by every state-changing command; pause/resume/stop and
        read-only commands stay available to the UI by design.

        Args:
            token: Lock token supplied by the caller. Empty for manual/UI calls.

        Raises:
            ExperimentLockError: If an experiment is active and the token does not match.
        """
        if self._experiment_state != "idle" and token != self._experiment_token:
            raise ExperimentLockError(
                "Rejected: an experiment script holds the gantry lock. "
                "Use the Pause/Stop controls, or pass the lock token "
                "returned by AcquireExperimentLock."
            )

    # ------------------------------------------------------------------
    # Observable properties
    # ------------------------------------------------------------------

    @sila.ObservableProperty()
    async def position(self) -> sila.Stream[Position]:
        """Current XYZ position of the gantry in mm."""
        while True:
            pos = await asyncio.to_thread(self._controller.get_position)
            yield Position(x=pos['x'], y=pos['y'], z=pos['z'])
            await asyncio.sleep(0.5)

    @sila.ObservableProperty()
    async def state(self) -> sila.Stream[str]:
        """Current state of the gantry (e.g. idle, moving, error)."""
        while True:
            yield await asyncio.to_thread(self._controller.get_state)
            await asyncio.sleep(0.5)

    @sila.ObservableProperty()
    async def current_workspace_yaml(self) -> sila.Stream[str]:
        """Raw YAML of the currently loaded workspace, empty string if none.

        Sourced from the controller's workspace manager, so it reflects
        workspaces loaded by name, from raw YAML, or restored at startup.
        """
        while True:
            yield self._controller.get_workspace_yaml()
            await asyncio.sleep(1.0)

    @sila.ObservableProperty()
    async def current_well(self) -> sila.Stream[str]:
        """Label of the well the gantry most recently moved to, e.g. 'plate1/A3'."""
        while True:
            yield self._current_well
            await asyncio.sleep(0.1)

    @sila.ObservableProperty()
    async def current_action(self) -> sila.Stream[str]:
        """Human-readable description of what the gantry is currently doing."""
        while True:
            yield self._current_action
            await asyncio.sleep(0.1)

    @sila.ObservableProperty()
    async def toolhead_info(self) -> sila.Stream[ToolheadInfo]:
        """Current toolhead geometry. active=False when no toolhead is configured."""
        while True:
            th = self._controller.get_toolhead()
            mounted = self._controller.toolhead_mounted
            mounted_all = "|".join(self._controller.get_mounted_toolheads())
            if th is None:
                yield ToolheadInfo(
                    active=False, name="", display_name="",
                    footprint_x=0.0, footprint_y=0.0,
                    offset_x=0.0, offset_y=0.0,
                    tip_offset_z=0.0, z_engage=0.0,
                    toolhead_mounted=mounted,
                    mounted_toolheads=mounted_all,
                )
            else:
                yield ToolheadInfo(
                    active=True,
                    name=self._controller.get_toolhead_name(),
                    display_name=self._controller.get_toolhead_display_name(),
                    footprint_x=th.footprint_x,
                    footprint_y=th.footprint_y,
                    offset_x=th.offset_x,
                    offset_y=th.offset_y,
                    tip_offset_z=th.tip_offset_z,
                    z_engage=th.z_engage,
                    tip_x=th.tip_x,
                    tip_y=th.tip_y,
                    toolhead_mounted=mounted,
                    mounted_toolheads=mounted_all,
                    calibrated_at=th.calibrated_at,
                )
            await asyncio.sleep(1.0)

    @sila.ObservableProperty()
    async def has_saved_state(self) -> sila.Stream[bool]:
        """True if calibrated limits from a previous clean shutdown are loaded."""
        while True:
            yield self._controller.has_saved_state
            await asyncio.sleep(2.0)

    @sila.ObservableProperty()
    async def experiment_active(self) -> sila.Stream[bool]:
        """True while a script experiment holds the lock. UI should disable manual controls."""
        while True:
            yield self._experiment_state != "idle"
            await asyncio.sleep(0.2)

    # ------------------------------------------------------------------
    # Motion commands
    # ------------------------------------------------------------------

    @sila.UnobservableCommand()
    async def move_to(self, x: float, y: float, z: float, token: str = "") -> None:
        """Move to an absolute position with safe clearance travel (raise -> XY -> lower).

        Args:
            X: Target x coordinate in mm. e.g. 150.0
            Y: Target y coordinate in mm. e.g. 200.0
            Z: Target z coordinate in mm. e.g. 50.0
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        self._current_action = f"Moving to ({x:.1f}, {y:.1f}, {z:.1f})"
        try:
            await self._run(self._controller.move_to, x, y, z, log="move_to", x=x, y=y, z=z)
            self._current_action = "Standby"
        except Exception as exc:
            self._current_action = f"Error: {exc}"
            raise

    @sila.UnobservableCommand()
    async def move_to_well(
        self, label: str, override_unvalidated: bool = False, token: str = ""
    ) -> None:
        """Move to a well by label using the active workspace.

        Args:
            Label: Well label, e.g. 'A3', 'H12', or 'plate1/A3'.
            OverrideUnvalidated: Proceed even if the active toolhead's geometry is
                unvalidated (placeholder). Defaults to refusing such moves.
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        self._current_action = f"Moving to {label}"
        try:
            await self._run(
                self._controller.move_to_well, label, override_unvalidated,
                log="move_to_well", well=label,
            )
            self._current_well = label
            self._current_action = "Standby"
        except Exception as exc:
            self._current_action = f"Error: {exc}"
            raise

    @sila.UnobservableCommand()
    async def jog(
        self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, token: str = ""
    ) -> None:
        """Move relative to the current position. No clearance sequence.

        Args:
            Dx: Relative X distance in mm. Positive = right. e.g. 10.0
            Dy: Relative Y distance in mm. Positive = forward. e.g. 10.0
            Dz: Relative Z distance in mm. Positive = up, negative = down. e.g. -5.0
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        try:
            await self._run(self._controller.jog, dx, dy, dz)
        except Exception as exc:
            self._current_action = f"Error: {exc}"
            raise

    @sila.UnobservableCommand()
    async def engage_tool(self, depth: float, token: str = "") -> None:
        """Lower the tool by a specified depth (mm) from the current position.

        Args:
            Depth: Distance in mm to lower the tool. e.g. 5.0
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        self._current_action = "Engaging tool"
        try:
            await self._run(self._controller.engage_tool, depth, log="engage_tool", depth=depth)
            self._current_action = "Standby"
        except Exception as exc:
            self._current_action = f"Error: {exc}"
            raise

    @sila.UnobservableCommand()
    async def disengage_tool(self, depth: float, token: str = "") -> None:
        """Raise the tool by a specified depth (mm) from the current position.

        Args:
            Depth: Distance in mm to raise the tool. e.g. 5.0
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        self._current_action = "Disengaging tool"
        try:
            await self._run(self._controller.disengage_tool, depth, log="disengage_tool", depth=depth)
            self._current_action = "Standby"
        except Exception as exc:
            self._current_action = f"Error: {exc}"
            raise

    @sila.UnobservableCommand()
    async def save_and_park(self, token: str = "") -> None:
        """Move to the park position and save homing state for the next session.

        Args:
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        self._current_action = "Parking"
        try:
            await self._run(self._controller.save_and_park, log="save_and_park")
            self._current_action = "Standby"
        except Exception as exc:
            self._current_action = f"Error: {exc}"
            raise

    # ------------------------------------------------------------------
    # Homing
    # ------------------------------------------------------------------

    # Homing commands are manual-only: they are always rejected while a script
    # holds the experiment lock (scripts never calibrate limits mid-run).

    @sila.UnobservableCommand()
    async def start_manual_homing(self) -> None:
        """Begin manual homing with a toolhead mounted."""
        self._check_lock()
        self._current_action = "Manual Homing"
        await self._run(self._controller.start_manual_homing, log="homing", step="start")

    @sila.UnobservableCommand()
    async def confirm_x_min(self) -> None:
        """Declare current X position as X=0 (left physical limit). Use whichever X corner you're at."""
        self._check_lock()
        await self._run(self._controller.confirm_x_min, log="homing", step="x_min")

    @sila.UnobservableCommand()
    async def confirm_x_max(self) -> None:
        """Declare current X position as the fixed x_max (right physical limit)."""
        self._check_lock()
        await self._run(self._controller.confirm_x_max, log="homing", step="x_max")

    @sila.UnobservableCommand()
    async def confirm_y_min(self) -> None:
        """Declare current Y position as Y=0 (front physical limit). Use whichever Y corner you're at."""
        self._check_lock()
        await self._run(self._controller.confirm_y_min, log="homing", step="y_min")

    @sila.UnobservableCommand()
    async def confirm_y_max(self) -> None:
        """Declare current Y position as the fixed y_max (back physical limit)."""
        self._check_lock()
        await self._run(self._controller.confirm_y_max, log="homing", step="y_max")

    @sila.UnobservableCommand()
    async def confirm_z_reference(self) -> None:
        """Declare current Z position as Z=0 (working reference surface)."""
        self._check_lock()
        await self._run(self._controller.confirm_z_reference, log="homing", step="z_reference")

    @sila.UnobservableCommand()
    async def finish_homing(self) -> None:
        """End manual homing mode and restore bounds checking."""
        self._check_lock()
        await self._run(self._controller.finish_homing, log="homing", step="finish")
        self._current_action = "Standby"

    @sila.UnobservableCommand()
    async def set_z(self, z: float) -> None:
        """Manually declare the current Z height without moving.

        Args:
            Z: Current Z height in mm. e.g. 50.0
        """
        self._check_lock()
        await self._run(self._controller.set_z, z)

    @sila.UnobservableCommand()
    async def get_limits(self) -> str:
        """Return calibrated axis limits + current safe clearance height as a
        pipe-delimited string: 'x_min|x_max|y_min|y_max|z_min|z_max|safe_clearance_z'.
        """
        return await asyncio.to_thread(self._controller.get_limits)

    # ------------------------------------------------------------------
    # Toolhead management
    # ------------------------------------------------------------------

    @sila.UnobservableCommand()
    async def set_toolhead(self, name: str, token: str = "") -> None:
        """Switch the active toolhead: load a config by name and apply its geometry.

        A pure software switch: per-head mount confirmations and homing state
        are preserved, so scripts can alternate between two mounted heads
        unattended. Confirm each physically installed head once with
        ConfirmToolheadMounted; the confirmation follows the head, not the switch.

        Args:
            Name: Toolhead name matching a config folder under toolheads/. e.g. ph_probe
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        await self._run(self._controller.set_toolhead, name, log="set_toolhead", toolhead=name)

    @sila.UnobservableCommand()
    async def clear_toolhead(self) -> None:
        """Remove the active toolhead and revert to bare carriage geometry."""
        self._check_lock()
        await self._run(self._controller.clear_toolhead, log="clear_toolhead")

    @sila.UnobservableCommand()
    async def confirm_toolhead_mounted(self, token: str = "") -> None:
        """Confirm that a toolhead is physically installed on the carriage.

        Args:
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        await self._run(self._controller.set_toolhead_mounted, True, log="toolhead_mounted", mounted=True)

    @sila.UnobservableCommand()
    async def clear_toolhead_mounted(self, token: str = "") -> None:
        """Declare that no toolhead is physically installed.

        Args:
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        await self._run(self._controller.set_toolhead_mounted, False, log="toolhead_mounted", mounted=False)

    @sila.UnobservableCommand()
    async def calibrate_toolhead_tip(
        self, measured_x: float, measured_y: float, wells: str, token: str = ""
    ) -> str:
        """Derive and persist the active toolhead's tip offset from measured well centre(s).

        Called after the operator jogs the physical tip to the centre of one
        or more calibration wells (typically a plate's corner wells); the
        averaged machine coordinates here are back-solved against the average
        of those wells' nominal positions into tip_x/tip_y, and the
        toolhead's geometry is marked validated. Returns the pipe-delimited
        string 'nominal_x|nominal_y|tip_x|tip_y' so the caller can show
        exactly what was measured and saved, not just fire-and-forget.

        Args:
            MeasuredX: Average machine X across the measured well centres.
            MeasuredY: Average machine Y across the measured well centres.
            Wells: Pipe-delimited 'plate_id/well_label' entries that were measured.
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        result = await self._run(
            self._controller.calibrate_toolhead_tip, measured_x, measured_y, wells,
            log="calibrate_toolhead_tip", measured_x=measured_x, measured_y=measured_y, wells=wells,
        )
        return f"{result['nominal_x']}|{result['nominal_y']}|{result['tip_x']}|{result['tip_y']}"

    @sila.UnobservableCommand()
    async def calibrate_toolhead_tip_z(self, measured_z: float, token: str = "") -> None:
        """Derive and persist the active toolhead's Z offset from a measured surface touch.

        Called after the operator lowers the tip until it touches the deck/
        reference surface (Z=0); the carriage Z reported here at that instant
        is persisted directly as tip_offset_z.

        Args:
            MeasuredZ: Carriage Z position in mm when the tip touches the Z=0 reference surface.
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        await self._run(
            self._controller.calibrate_toolhead_tip_z, measured_z,
            log="calibrate_toolhead_tip_z", measured_z=measured_z,
        )

    @sila.UnobservableCommand()
    async def list_toolheads(self) -> str:
        """Return installed toolhead configs as newline-delimited 'name|display_name' entries."""
        entries = await asyncio.to_thread(self._controller.list_toolheads)
        return "\n".join(f"{n}|{d}" for n, d in entries)

    # ------------------------------------------------------------------
    # Workspace management
    # ------------------------------------------------------------------

    @sila.UnobservableCommand()
    async def set_workspace(self, name: str, token: str = "") -> None:
        """Load a workspace config by name from the bundled definitions directory.

        Args:
            Name: Workspace name matching a file in workspace/definitions/. e.g. plate_96well
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        await asyncio.to_thread(self._controller.set_workspace, name)
        self._log.log("load_workspace", source=name)

    @sila.UnobservableCommand()
    async def load_workspace_yaml(self, content: str, token: str = "") -> None:
        """Load a workspace config from raw YAML content.

        Args:
            Content: Full YAML content of a workspace definition.
            Token: Experiment lock token from AcquireExperimentLock. Empty for manual calls.
        """
        self._check_lock(token)
        await asyncio.to_thread(self._controller.load_workspace_from_yaml, content)
        self._log.log("load_workspace", source="yaml")

    @sila.UnobservableCommand()
    async def get_workspace_yaml(self) -> str:
        """Return the raw YAML of the currently loaded workspace, or empty string if none."""
        return self._controller.get_workspace_yaml()

    @sila.UnobservableCommand()
    async def list_workspaces(self) -> str:
        """Return available workspace config names as a newline-delimited list."""
        entries = await asyncio.to_thread(self._controller.list_workspaces)
        return "\n".join(entries)

    @sila.UnobservableCommand()
    async def get_labware(self) -> str:
        """Return all bundled labware (plate geometry) definitions as one YAML document.

        Single source of truth for plate dimensions - the frontend deck canvas
        and experiment scripts fetch this instead of hardcoding geometry.
        """
        return await asyncio.to_thread(self._controller.get_labware_yaml)

    # ------------------------------------------------------------------
    # Experiment lock
    # ------------------------------------------------------------------

    @sila.UnobservableCommand()
    async def acquire_experiment_lock(self) -> str:
        """Claim exclusive experiment control. Fails if another script is already running.

        Returns a secret token; pass it as the Token parameter of motion,
        toolhead, and workspace commands so they are accepted while the lock is
        held. Everything without the token is rejected until release.
        """
        if self._experiment_state != "idle":
            raise ExperimentLockError(
                "An experiment is already running. "
                "Only one script may hold the experiment lock at a time."
            )
        self._experiment_state = "running"
        self._experiment_token = uuid.uuid4().hex
        self._log.log("experiment_start")
        return self._experiment_token

    @sila.UnobservableCommand()
    async def release_experiment_lock(self, token: str = "") -> None:
        """Release experiment control and return to idle.

        Args:
            Token: The lock token returned by AcquireExperimentLock.
        """
        if self._experiment_state == "idle":
            return
        if token != self._experiment_token:
            raise ExperimentLockError(
                "Rejected: only the lock holder may release the experiment lock."
            )
        self._experiment_state = "idle"
        self._experiment_token = ""
        self._log.log("experiment_end")

    @sila.UnobservableCommand()
    async def force_release_experiment_lock(self) -> None:
        """Forcibly release the experiment lock without the holder's token.

        Recovery command for when the lock-holding script died without
        releasing (killed process, crashed terminal): the token dies with the
        process, and without this the lock would stay stuck until a server
        restart. Tokenless by design, same trust model as StopExperiment -
        coordination between cooperating clients, not authentication.
        """
        if self._experiment_state == "idle":
            return
        self._log.log("experiment_force_release", previous_state=self._experiment_state)
        self._experiment_state = "idle"
        self._experiment_token = ""

    @sila.UnobservableCommand()
    async def pause_experiment(self) -> None:
        """Signal the running script to pause between wells."""
        if self._experiment_state == "running":
            self._experiment_state = "paused"

    @sila.UnobservableCommand()
    async def resume_experiment(self) -> None:
        """Resume a paused experiment."""
        if self._experiment_state == "paused":
            self._experiment_state = "running"

    @sila.UnobservableCommand()
    async def stop_experiment(self) -> None:
        """Signal the running script to stop after the current well."""
        if self._experiment_state in ("running", "paused"):
            self._experiment_state = "stop_requested"

    @sila.UnobservableCommand()
    async def get_experiment_state(self) -> str:
        """Return the current experiment state: idle | running | paused | stop_requested."""
        return self._experiment_state
