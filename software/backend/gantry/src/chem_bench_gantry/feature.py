"""SiLA2 feature for the Gantry."""
import asyncio
import dataclasses

from unitelabs.cdk import sila

from chem_bench_gantry.interfaces import GantryControllerProtocol


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


class Gantry(sila.Feature):

    def __init__(self, controller: GantryControllerProtocol):
        super().__init__(
            originator="edu.iastate.ames",
            category="rxnbench",
            version="0.1",
            maturity_level="Draft",
        )
        self._controller = controller
        self._hw_lock = asyncio.Lock()
        self._current_well:   str = ""
        self._current_action: str = "Standby"

    async def _run(self, fn, *args, **kwargs):
        async with self._hw_lock:
            return await asyncio.to_thread(fn, *args, **kwargs)

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
    async def current_well(self) -> sila.Stream[str]:
        """Label of the well the gantry most recently moved to, e.g. 'plate1/A3'."""
        last = object()
        while True:
            if self._current_well is not last:
                last = self._current_well
                yield self._current_well
            await asyncio.sleep(0.1)

    @sila.ObservableProperty()
    async def current_action(self) -> sila.Stream[str]:
        """Human-readable description of what the gantry is currently doing."""
        last = object()
        while True:
            if self._current_action is not last:
                last = self._current_action
                yield self._current_action
            await asyncio.sleep(0.1)

    @sila.ObservableCommand()
    async def move_to(self, x: float, y: float, z: float) -> None:
        """Move to an absolute position with safe clearance travel (raise -> XY -> lower).

        Args:
            X: Target x coordinate in mm. e.g. 150.0
            Y: Target y coordinate in mm. e.g. 200.0
            Z: Target z coordinate in mm. e.g. 50.0
        """
        self._current_action = f"Moving to ({x:.1f}, {y:.1f}, {z:.1f})"
        try:
            await self._run(self._controller.move_to, x, y, z)
        finally:
            self._current_action = "Standby"

    @sila.ObservableCommand()
    async def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        """Move relative to the current position. No clearance sequence.

        Args:
            Dx: Relative X distance in mm. Positive = right. e.g. 10.0
            Dy: Relative Y distance in mm. Positive = forward. e.g. 10.0
            Dz: Relative Z distance in mm. Positive = up, negative = down. e.g. -5.0
        """
        await self._run(self._controller.jog, dx, dy, dz)

    @sila.ObservableCommand()
    async def engage_tool(self, depth: float) -> None:
        """Lower the tool by a specified depth (mm) from the current position.

        Args:
            Depth: Distance in mm to lower the tool. e.g. 5.0
        """
        self._current_action = "Engaging tool"
        try:
            await self._run(self._controller.engage_tool, depth)
        finally:
            self._current_action = "Standby"

    @sila.ObservableCommand()
    async def disengage_tool(self, depth: float) -> None:
        """Raise the tool by a specified depth (mm) from the current position.

        Args:
            Depth: Distance in mm to raise the tool. e.g. 5.0
        """
        self._current_action = "Disengaging tool"
        try:
            await self._run(self._controller.disengage_tool, depth)
        finally:
            self._current_action = "Standby"

    @sila.UnobservableCommand()
    async def start_manual_homing(self) -> None:
        """Begin manual homing with a toolhead mounted."""
        self._current_action = "Manual Homing"
        await self._run(self._controller.start_manual_homing)

    @sila.UnobservableCommand()
    async def confirm_x_min(self) -> None:
        """Declare current X position as X=0 (left physical limit)."""
        await self._run(self._controller.confirm_x_min)

    @sila.UnobservableCommand()
    async def confirm_x_max(self) -> None:
        """Record current X position as the right physical limit."""
        await self._run(self._controller.confirm_x_max)

    @sila.UnobservableCommand()
    async def confirm_y_min(self) -> None:
        """Declare current Y position as Y=0 (front physical limit)."""
        await self._run(self._controller.confirm_y_min)

    @sila.UnobservableCommand()
    async def confirm_y_max(self) -> None:
        """Record current Y position as the back physical limit."""
        await self._run(self._controller.confirm_y_max)

    @sila.UnobservableCommand()
    async def confirm_z_reference(self) -> None:
        """Declare current Z position as Z=0 (working reference surface)."""
        await self._run(self._controller.confirm_z_reference)

    @sila.UnobservableCommand()
    async def finish_homing(self) -> None:
        """End manual homing mode and restore bounds checking."""
        await self._run(self._controller.finish_homing)
        self._current_action = "Standby"

    @sila.UnobservableCommand()
    async def set_z(self, z: float) -> None:
        """Manually declare the current Z height without moving.

        Args:
            Z: Current Z height in mm. e.g. 50.0
        """
        await self._run(self._controller.set_z, z)

    @sila.ObservableProperty()
    async def toolhead_info(self) -> sila.Stream[ToolheadInfo]:
        """Current toolhead geometry. active=False when no toolhead is configured."""
        while True:
            th = self._controller.get_toolhead()
            mounted = self._controller.toolhead_mounted
            if th is None:
                yield ToolheadInfo(
                    active=False, name="", display_name="",
                    footprint_x=0.0, footprint_y=0.0,
                    offset_x=0.0, offset_y=0.0,
                    tip_offset_z=0.0, z_engage=0.0,
                    toolhead_mounted=mounted,
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
                )
            await asyncio.sleep(1.0)

    @sila.UnobservableCommand()
    async def set_toolhead(self, name: str) -> None:
        """Load a toolhead config by name and apply its geometry.

        Args:
            Name: Toolhead name matching a config folder under toolheads/. e.g. ph_probe
        """
        await self._run(self._controller.set_toolhead, name)

    @sila.UnobservableCommand()
    async def clear_toolhead(self) -> None:
        """Remove the active toolhead and revert to bare carriage geometry."""
        await self._run(self._controller.clear_toolhead)

    @sila.UnobservableCommand()
    async def confirm_toolhead_mounted(self) -> None:
        """Confirm that a toolhead is physically installed on the carriage."""
        await self._run(self._controller.set_toolhead_mounted, True)

    @sila.UnobservableCommand()
    async def clear_toolhead_mounted(self) -> None:
        """Declare that no toolhead is physically installed."""
        await self._run(self._controller.set_toolhead_mounted, False)

    @sila.UnobservableCommand()
    async def list_toolheads(self) -> str:
        """Return installed toolhead configs as newline-delimited 'name|display_name' entries."""
        entries = await asyncio.to_thread(self._controller.list_toolheads)
        return "\n".join(f"{n}|{d}" for n, d in entries)

    @sila.UnobservableCommand()
    async def set_workspace(self, name: str) -> None:
        """Load a workspace config by name from the bundled definitions directory.

        Args:
            Name: Workspace name matching a file in workspace/definitions/. e.g. plate_96well
        """
        await asyncio.to_thread(self._controller.set_workspace, name)

    @sila.UnobservableCommand()
    async def load_workspace_yaml(self, content: str) -> None:
        """Load a workspace config from raw YAML content.

        Args:
            Content: Full YAML content of a workspace definition.
        """
        await asyncio.to_thread(self._controller.load_workspace_from_yaml, content)

    @sila.ObservableCommand()
    async def move_to_well(self, label: str) -> None:
        """Move to a well by label using the active workspace.

        Args:
            Label: Well label, e.g. 'A3', 'H12', or 'plate1/A3'.
        """
        self._current_action = f"Moving to {label}"
        try:
            await self._run(self._controller.move_to_well, label)
            self._current_well = label
        finally:
            self._current_action = "Standby"

    @sila.UnobservableCommand()
    async def list_workspaces(self) -> str:
        """Return available workspace config names as a newline-delimited list."""
        entries = await asyncio.to_thread(self._controller.list_workspaces)
        return "\n".join(entries)

    @sila.ObservableProperty()
    async def has_saved_state(self) -> sila.Stream[bool]:
        """True if calibrated limits from a previous clean shutdown are loaded."""
        while True:
            yield self._controller.has_saved_state
            await asyncio.sleep(2.0)

    @sila.UnobservableCommand()
    async def save_and_park(self) -> None:
        """Move to the park position and save homing state for the next session."""
        self._current_action = "Parking"
        try:
            await self._run(self._controller.save_and_park)
        finally:
            self._current_action = "Standby"

    @sila.UnobservableCommand()
    async def get_limits(self) -> str:
        """Return calibrated axis limits as a pipe-delimited string: 'x_min|x_max|y_min|y_max|z_min|z_max'."""
        return await asyncio.to_thread(self._controller.get_limits)
