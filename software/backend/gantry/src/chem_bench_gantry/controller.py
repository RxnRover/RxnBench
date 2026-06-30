"""Thin orchestrator above MotionEngine, HomingManager, ToolheadManager, and WorkspaceManager."""
from typing import Any

from chem_bench_gantry.interfaces import MotionClientProtocol
from chem_bench_gantry.toolhead_config import ToolheadGeometry
from chem_bench_gantry.errors import MotionLimitError
from chem_bench_gantry.toolhead_manager import ToolheadManager
from chem_bench_gantry.homing_manager import HomingManager
from chem_bench_gantry.motion_engine import MotionEngine
from chem_bench_gantry.workspace_manager import WorkspaceManager


class GantryController:

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
        sensor_registry: dict[str, Any] | None = None,
    ):
        self._sensor_registry: dict[str, Any] = sensor_registry or {}
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
        tip_z   = th.tip_offset_z if th else 0.0

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
        if self._homing_mgr.homing_active:
            self._homing_mgr.homing_jog_update(dx, dy, dz)
        else:
            if dx != 0.0 or dy != 0.0 or dz != 0.0:
                pos = self._engine.get_position()
                self._check_bounds(
                    x=pos['x'] + dx if dx != 0.0 else None,
                    y=pos['y'] + dy if dy != 0.0 else None,
                    z=pos['z'] + dz if dz != 0.0 else None,
                )
        self._engine.jog(dx, dy, dz, speed)

    def engage_tool(self, depth: float, speed: float | None = None) -> None:
        pos = self._engine.get_position()
        target_z = pos['z'] - depth
        self._check_bounds(z=target_z)
        self._engine.move(z=target_z, speed=speed)

    def disengage_tool(self, depth: float, speed: float | None = None) -> None:
        pos = self._engine.get_position()
        target_z = pos['z'] + depth
        self._check_bounds(z=target_z)
        self._engine.move(z=target_z, speed=speed)

    def get_position(self) -> dict[str, float]:
        return self._engine.get_position()

    def get_state(self) -> str:
        return self._engine.get_state()

    def save_and_park(self) -> None:
        h = self._homing_mgr
        try:
            self._engine.move(z=self._safe_clearance_z)
            self._engine.move(x=h.x_min, y=h.y_min)
        except Exception:
            pass
        h.save(toolhead_name=self._toolhead_mgr.name)

    def home_auto(self) -> None:
        self._homing_mgr.home_auto(self._safe_clearance_z)

    def start_manual_homing(self) -> None:
        self._homing_mgr.start_manual_homing()

    def confirm_x_min(self) -> None:
        self._homing_mgr.confirm_x_min()

    def confirm_x_max(self) -> None:
        self._homing_mgr.confirm_x_max()

    def confirm_y_min(self) -> None:
        self._homing_mgr.confirm_y_min()

    def confirm_y_max(self) -> None:
        self._homing_mgr.confirm_y_max()

    def confirm_z_reference(self) -> None:
        self._homing_mgr.confirm_z_reference()

    def finish_homing(self) -> None:
        self._homing_mgr.finish_homing()

    def set_z(self, z: float) -> None:
        self._homing_mgr.set_z(z)

    def get_toolhead(self) -> ToolheadGeometry | None:
        return self._toolhead_mgr.toolhead

    def get_toolhead_name(self) -> str:
        return self._toolhead_mgr.name

    def get_toolhead_display_name(self) -> str:
        return self._toolhead_mgr.display_name

    def set_toolhead(self, name: str) -> None:
        self._toolhead_mgr.set_toolhead(name)
        self._homing_mgr.invalidate_state()

    def clear_toolhead(self) -> None:
        self._toolhead_mgr.clear_toolhead()

    def set_toolhead_mounted(self, mounted: bool) -> None:
        self._toolhead_mgr.set_mounted(mounted)

    def list_toolheads(self) -> list[tuple[str, str]]:
        return ToolheadManager.list_toolheads()

    def get_limits(self) -> str:
        h = self._homing_mgr
        return f"{h.x_min}|{h.x_max}|{h.y_min}|{h.y_max}|{h.z_min}|{h.z_max}"

    def get_toolhead_sensor(self) -> Any:
        sensor_type = self._toolhead_mgr.sensor_type
        if not sensor_type:
            return None
        return self._sensor_registry.get(sensor_type)

    def set_workspace(self, name: str) -> None:
        self._workspace_mgr.load(name)

    def load_workspace_from_yaml(self, content: str) -> None:
        self._workspace_mgr.load_from_yaml(content)

    def move_to_well(self, label: str) -> None:
        x, y, _z = self._workspace_mgr.resolve_well(label)
        self.move_to(x=x, y=y)

    def list_workspaces(self) -> list[str]:
        return WorkspaceManager.list_available()

    def get_workspace_name(self) -> str:
        return self._workspace_mgr.name
