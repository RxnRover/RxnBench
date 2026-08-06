"""Structural (Protocol) interfaces for the gantry motion layer."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from rxn_bench_gantry.toolhead_config import ToolheadGeometry


@runtime_checkable
class MotionClientProtocol(Protocol):
    """Low-level hardware motion client. Satisfied by MoonrakerClient and MockMoonrakerClient."""

    def set_kinematic_position(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        """Tell the firmware the current position for the given axes without physically moving."""
        ...

    def home(self, axes: str = "XY") -> None:
        """Home the specified axes. Never pass Z - no probe is attached."""
        ...

    def move(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None:
        """Move to absolute machine coordinates (mm) and block until complete."""
        ...

    def jog(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        speed: float | None = None,
    ) -> None:
        """Move relative to the current position. No clearance sequence."""
        ...

    def get_position(self) -> dict[str, float]:
        """Return the current XYZ machine position as ``{'x': ..., 'y': ..., 'z': ...}``."""
        ...

    def get_homed_axes(self) -> str:
        """Return which axes are currently homed, e.g. ``'xy'``, ``'xyz'``, or ``''``."""
        ...

    def get_axis_limits(self) -> dict[str, tuple[float, float]]:
        """Return firmware axis limits as ``{axis: (min, max)}``."""
        ...

    def get_state(self) -> str:
        """Return the firmware state string, e.g. ``'ready'`` or ``'error'``."""
        ...

    def gcode(self, script: str) -> None:
        """Send a raw GCode script and block until it finishes."""
        ...


@runtime_checkable
class GantryControllerProtocol(Protocol):
    """High-level gantry controller interface used by the Gantry SiLA feature.

    Satisfied by GantryController. Consume this type in SiLA features rather than the
    concrete class so tests can substitute a lightweight fake.
    """

    @property
    def has_saved_state(self) -> bool: ...

    @property
    def toolhead_mounted(self) -> bool: ...

    def get_position(self) -> dict[str, float]: ...

    def get_state(self) -> str: ...

    def move_to(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        speed: float | None = None,
    ) -> None: ...

    def jog(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        speed: float | None = None,
    ) -> None: ...

    def engage_tool(self, depth: float, speed: float | None = None) -> None: ...

    def disengage_tool(self, depth: float, speed: float | None = None) -> None: ...

    def home_auto(self) -> None: ...

    def start_manual_homing(self) -> None: ...

    def confirm_x_min(self) -> None: ...

    def confirm_x_max(self) -> None: ...

    def confirm_y_min(self) -> None: ...

    def confirm_y_max(self) -> None: ...

    def confirm_z_reference(self) -> None: ...

    def finish_homing(self) -> None: ...

    def set_z(self, z: float) -> None: ...

    def get_toolhead(self) -> ToolheadGeometry | None: ...

    def get_toolhead_name(self) -> str: ...

    def get_toolhead_display_name(self) -> str: ...

    def set_toolhead(self, name: str) -> None: ...

    def clear_toolhead(self) -> None: ...

    def set_toolhead_mounted(self, mounted: bool) -> None: ...

    def get_mounted_toolheads(self) -> list[str]: ...

    def list_toolheads(self) -> list[tuple[str, str]]: ...

    def save_and_park(self) -> None: ...

    def get_limits(self) -> str: ...

    def set_workspace(self, name: str) -> None: ...

    def load_workspace_from_yaml(self, content: str) -> None: ...

    def move_to_well(self, label: str, override_unvalidated: bool = False) -> dict[str, float]: ...

    def list_workspaces(self) -> list[str]: ...

    def get_workspace_name(self) -> str: ...

    def get_workspace_yaml(self) -> str: ...

    def get_labware_yaml(self) -> str: ...
