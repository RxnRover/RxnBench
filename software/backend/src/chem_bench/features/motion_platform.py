"""
SiLA2 feature for the Motion Platform.

Exposes motion control and status as SiLA endpoints.
Hardware communication is handled by MotionPlatformController.

Author: John Brittain
Date: Jun 17 2026
"""

import asyncio
import dataclasses

from unitelabs.cdk import sila

from chem_bench.io.motion_platform.motion_platform_controller import MotionPlatformController


@dataclasses.dataclass
class Position:
    """XYZ position of the motion platform in mm."""
    x: float
    y: float
    z: float


@dataclasses.dataclass
class ToolheadInfo:
    """Current toolhead geometry streamed as an ObservableProperty.

    active=False with all zeros means no toolhead is mounted.
    """
    active: bool
    name: str
    display_name: str
    footprint_x: float
    footprint_y: float
    offset_x: float
    offset_y: float
    tip_offset_z: float
    z_engage: float


class MotionPlatform(sila.Feature):

    def __init__(self, controller: MotionPlatformController):
        super().__init__(
            originator="edu.iastate.ames",
            category="chembench",
            version="0.1",
            maturity_level="Draft",
        )
        self._controller = controller

    @sila.ObservableProperty()
    async def position(self) -> sila.Stream[Position]:
        """Current XYZ position of the motion platform in mm.

        Returns:
            Position: Current x, y, z coordinates.
        """
        while True:
            pos = self._controller.get_position()
            yield Position(x=pos['x'], y=pos['y'], z=pos['z'])
            await asyncio.sleep(0.5)

    @sila.ObservableProperty()
    async def state(self) -> sila.Stream[str]:
        """Current state of the motion controller (e.g. idle, moving, error).

        Returns:
            State: Current state string.
        """
        while True:
            yield self._controller.get_state()
            await asyncio.sleep(0.5)

    @sila.ObservableCommand()
    async def move_to(self, x: float, y: float, z: float) -> None:
        """Move to an absolute position with safe clearance travel (raise -> XY -> lower).

        Args:
            X: Target x coordinate in mm.
            Y: Target y coordinate in mm.
            Z: Target z coordinate in mm.
        """
        self._controller.move_to(x, y, z)

    @sila.ObservableCommand()
    async def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        """Move relative to the current position. No clearance sequence - use for manual positioning.

        Args:
            Dx: Relative X distance in mm.
            Dy: Relative Y distance in mm.
            Dz: Relative Z distance in mm. Negative moves down.
        """
        self._controller.jog(dx, dy, dz)

    @sila.ObservableCommand()
    async def engage_tool(self, depth: float) -> None:
        """Lower the tool by a specified depth (mm) from the current position.

        Args:
            Depth: Distance in mm to lower the tool.
        """
        self._controller.engage_tool(depth)

    @sila.ObservableCommand()
    async def disengage_tool(self, depth: float) -> None:
        """Raise the tool by a specified depth (mm) from the current position.

        Args:
            Depth: Distance in mm to raise the tool.
        """
        self._controller.disengage_tool(depth)

    """
Homing procedure
----------------
Toolhead NOT mounted (gantry clear):
  1. HomeAuto        - drives to XY endstops
  2. Attach toolhead
  3. Jog Z down to reference surface
  4. ConfirmZReference

Toolhead already mounted:
  1. StartManualHoming  - declares current position as X=150 Y=150 Z=150 (just to start)
  2. Jog X left until it stops -> ConfirmXMin
  3. Jog X right until it stops -> ConfirmXMax
  4. Jog Y to front limit -> ConfirmYMin
  5. Jog Y to back limit  -> ConfirmYMax
  6. Jog Z down to reference surface -> ConfirmZReference"""

    @sila.UnobservableCommand()
    async def home_auto(self) -> None:
        """Home XY via endstops. Only use when no toolhead is mounted."""
        self._controller.home_auto()

    @sila.UnobservableCommand()
    async def start_manual_homing(self) -> None:
        """Begin manual homing with a toolhead mounted.

        Declares current position as X=150 Y=150 Z=150 so jogging works.
        Then jog to each physical limit and call the corresponding Confirm command.
        """
        self._controller.start_manual_homing()

    @sila.UnobservableCommand()
    async def confirm_x_min(self) -> None:
        """Declare current X position as X=0 (left physical limit)."""
        self._controller.confirm_x_min()

    @sila.UnobservableCommand()
    async def confirm_x_max(self) -> None:
        """Record current X position as the right physical limit."""
        self._controller.confirm_x_max()

    @sila.UnobservableCommand()
    async def confirm_y_min(self) -> None:
        """Declare current Y position as Y=0 (front physical limit)."""
        self._controller.confirm_y_min()

    @sila.UnobservableCommand()
    async def confirm_y_max(self) -> None:
        """Record current Y position as the back physical limit."""
        self._controller.confirm_y_max()

    @sila.UnobservableCommand()
    async def confirm_z_reference(self) -> None:
        """Declare current Z position as Z=0 (working reference surface)."""
        self._controller.confirm_z_reference()

    @sila.UnobservableCommand()
    async def finish_homing(self) -> None:
        """End manual homing mode and restore bounds checking."""
        self._controller.finish_homing()

    @sila.UnobservableCommand()
    async def set_z(self, z: float) -> None:
        """Manually declare the current Z height without moving. Quick alternative to ConfirmZReference.

        Args:
            Z: Current Z height in mm.
        """
        self._controller.set_z(z)

    # ── Toolhead management ────────────────────────────────────────────────────

    @sila.ObservableProperty()
    async def toolhead_info(self) -> sila.Stream[ToolheadInfo]:
        """Current toolhead geometry. active=False when no toolhead is set.

        Returns:
            ToolheadInfo: footprint, offsets, tip depth, and engage depth in mm.
        """
        while True:
            th = self._controller.get_toolhead()
            if th is None:
                yield ToolheadInfo(
                    active=False, name="", display_name="",
                    footprint_x=0.0, footprint_y=0.0,
                    offset_x=0.0, offset_y=0.0,
                    tip_offset_z=0.0, z_engage=0.0,
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
                )
            await asyncio.sleep(1.0)

    @sila.UnobservableCommand()
    async def set_toolhead(self, name: str) -> None:
        """Load a toolhead config by name and apply its geometry.

        Args:
            Name: Toolhead name matching a config folder under io/toolheads/.
        """
        self._controller.set_toolhead(name)

    @sila.UnobservableCommand()
    async def clear_toolhead(self) -> None:
        """Remove the active toolhead and revert to bare carriage geometry."""
        self._controller.clear_toolhead()

    @sila.UnobservableCommand()
    async def list_toolheads(self) -> str:
        """Return installed toolhead configs as 'name|display_name' lines, one per toolhead.

        Returns:
            Toolheads: newline-delimited list of 'name|display_name' entries.
        """
        entries = self._controller.list_toolheads()
        return "\n".join(f"{n}|{d}" for n, d in entries)
