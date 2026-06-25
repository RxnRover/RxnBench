"""
Interface contracts for the motion layer.

MotionClientProtocol  — the surface MoonrakerClient and MockMoonrakerClient must satisfy.
                         GantryController depends on this, not on a concrete client.

GantryControllerProtocol — the surface Gantry (SiLA feature) depends on.
                            Decouples the feature from the concrete controller so an
                            alternative gantry implementation can be swapped in without
                            touching the feature code.

Author: John Brittain
Date: Jun 18 2026
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from chem_bench.io.toolheads.toolhead_config import ToolheadGeometry


@runtime_checkable
class MotionClientProtocol(Protocol):
    """Low-level motion hardware client.

    Implemented by MoonrakerClient (real hardware) and MockMoonrakerClient
    (in-memory simulation).  GantryController depends on this interface,
    not on either concrete class.
    """

    def set_kinematic_position(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None: ...

    def home(self, axes: str = "XY") -> None: ...

    def move(
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

    def get_position(self) -> dict[str, float]: ...

    def get_homed_axes(self) -> str: ...

    def get_axis_limits(self) -> dict[str, tuple[float, float]]: ...

    def get_state(self) -> str: ...

    def gcode(self, script: str) -> None: ...


@runtime_checkable
class GantryControllerProtocol(Protocol):
    """High-level gantry controller interface.

    Implemented by GantryController.  The Gantry SiLA feature depends on this
    interface so a different gantry controller can be substituted without
    modifying any feature code.
    """

    # --- state ---

    @property
    def has_saved_state(self) -> bool: ...

    @property
    def toolhead_mounted(self) -> bool: ...

    # --- position / state queries ---

    def get_position(self) -> dict[str, float]: ...

    def get_state(self) -> str: ...

    # --- motion ---

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

    # --- homing ---

    def home_auto(self) -> None: ...

    def start_manual_homing(self) -> None: ...

    def confirm_x_min(self) -> None: ...

    def confirm_x_max(self) -> None: ...

    def confirm_y_min(self) -> None: ...

    def confirm_y_max(self) -> None: ...

    def confirm_z_reference(self) -> None: ...

    def finish_homing(self) -> None: ...

    def set_z(self, z: float) -> None: ...

    # --- toolhead management ---

    def get_toolhead(self) -> ToolheadGeometry | None: ...

    def get_toolhead_name(self) -> str: ...

    def get_toolhead_display_name(self) -> str: ...

    def set_toolhead(self, name: str) -> None: ...

    def clear_toolhead(self) -> None: ...

    def set_toolhead_mounted(self, mounted: bool) -> None: ...

    def list_toolheads(self) -> list[tuple[str, str]]: ...

    # --- session persistence ---

    def save_and_park(self) -> None: ...

    # --- machine limits ---

    def get_limits(self) -> str: ...

    # --- toolhead sensor ---

    def get_toolhead_sensor(self) -> Any: ...

    # --- workspace ---

    def set_workspace(self, name: str) -> None: ...

    def load_workspace_from_yaml(self, content: str) -> None: ...

    def move_to_well(self, label: str) -> None: ...

    def list_workspaces(self) -> list[str]: ...

    def get_workspace_name(self) -> str: ...
