"""Gantry connection - human-maintained layer on top of the generated base.

Wire and command boilerplate lives in GantryConnectionBase (generated from
connection_spec.yaml).  Add convenience methods, custom decode logic,
and higher-level workflows here.
"""
from __future__ import annotations

import dataclasses
import threading
from typing import Any

import yaml
from PySide6.QtCore import Signal

from rxn_bench_ui.connections.base import _format_error

from .generated_connection import GantryConnectionBase
from .proto import motion_platform_pb2 as _mp


@dataclasses.dataclass
class ToolheadInfo:
    """Current toolhead geometry received from the SiLA ToolheadInfo observable."""
    active: bool           = False
    name: str              = ""
    display_name: str      = ""
    footprint_x: float     = 0.0
    footprint_y: float     = 0.0
    offset_x: float        = 0.0
    offset_y: float        = 0.0
    tip_offset_z: float    = 0.0
    z_engage: float        = 0.0
    tip_x: float           = 0.0
    tip_y: float           = 0.0
    toolhead_mounted: bool = False
    # Every head confirmed mounted (per-head state, survives activation switches).
    mounted_toolheads: tuple[str, ...] = ()


class GantryConnection(GantryConnectionBase):
    """Human-owned gantry client.

    Add convenience methods, nicer error handling, and higher-level workflows
    here.  Wire/command boilerplate is in GantryConnectionBase (generated).
    """

    limits_updated    = Signal(float, float, float, float, float, float)
    labware_updated   = Signal(object)     # dict: plate_type -> geometry dict, server-sourced
    workspace_op_done = Signal(bool, str)  # (ok, message) after apply/load workspace ops

    # --- Custom stream handlers ---

    def _handle_toolhead(self, resp: Any) -> None:
        th = resp.ToolheadInfo
        self.toolhead_updated.emit(ToolheadInfo(
            active           = th.active.value,
            name             = th.name.value,
            display_name     = th.display_name.value,
            footprint_x      = th.footprint_x.value,
            footprint_y      = th.footprint_y.value,
            offset_x         = th.offset_x.value,
            offset_y         = th.offset_y.value,
            tip_offset_z     = th.tip_offset_z.value,
            z_engage         = th.z_engage.value,
            tip_x            = th.tip_x.value,
            tip_y            = th.tip_y.value,
            toolhead_mounted = th.toolhead_mounted.value,
            mounted_toolheads=tuple(
                n for n in th.mounted_toolheads.value.split("|") if n
            ),
        ))

    def _handle_action(self, resp: Any) -> None:
        action = resp.CurrentAction.value
        self.action_changed.emit(action)
        if action.startswith("Error:"):
            self.error_occurred.emit(action[len("Error:"):].strip())

    # --- Post-connect setup ---

    def _after_connected(self, gen: int) -> None:
        if self._gen == gen:
            limits = self.fetch_limits()
            if limits is not None:
                self.limits_updated.emit(*limits)
            labware = self.fetch_labware()
            if labware:
                self.labware_updated.emit(labware)

    # --- Workspace operations (non-blocking, report via workspace_op_done) ---

    def apply_workspace_yaml(self, content: str) -> None:
        """Send raw workspace YAML to the server. Emits workspace_op_done(ok, msg)."""
        _p = _mp.LoadWorkspaceYaml_Parameters()
        _p.content.value = content
        self._workspace_op("LoadWorkspaceYaml", _p.SerializeToString(), "Workspace applied.")

    def load_workspace_by_name(self, name: str) -> None:
        """Load a bundled workspace by name. Emits workspace_op_done(ok, msg)."""
        _p = _mp.SetWorkspace_Parameters()
        _p.name.value = name
        self._workspace_op("SetWorkspace", _p.SerializeToString(), f"Workspace '{name}' loaded.")

    def _workspace_op(self, rpc: str, payload: bytes, ok_msg: str) -> None:
        def _do() -> None:
            try:
                self._channel.unary_unary(self._rpc(rpc))(payload, timeout=6.0)
                self.workspace_op_done.emit(True, ok_msg)
            except Exception as e:
                self.workspace_op_done.emit(False, _format_error(rpc, e))
        threading.Thread(target=_do, daemon=True).start()

    # --- Blocking fetches (call from QThread workers, not the main thread) ---

    def fetch_toolhead_list(self) -> list[tuple[str, str]]:
        """Fetch the list of configured toolheads from the server. Blocking - call from a worker thread."""
        try:
            raw  = self._channel.unary_unary(self._rpc("ListToolheads"))(b"", timeout=5.0)
            resp = _mp.ListToolheads_Responses.FromString(bytes(raw))
            result = []
            for line in resp.Toolheads.value.splitlines():
                parts = line.split("|", 1)
                if len(parts) == 2:
                    result.append((parts[0].strip(), parts[1].strip()))
            return result
        except Exception as e:
            self.error_occurred.emit(f"fetch_toolhead_list: {e}")
            return []

    def fetch_workspace_list(self) -> list[str]:
        """Fetch available workspace names from the server. Blocking - call from a worker thread."""
        try:
            raw  = self._channel.unary_unary(self._rpc("ListWorkspaces"))(b"", timeout=5.0)
            resp = _mp.ListWorkspaces_Responses.FromString(bytes(raw))
            return [w for w in resp.Workspaces.value.splitlines() if w]
        except Exception as e:
            self.error_occurred.emit(f"fetch_workspace_list: {e}")
            return []

    def fetch_labware(self) -> dict:
        """Fetch plate geometry definitions from the server. Blocking - call from a worker thread.

        Returns:
            Dict mapping plate type name to its geometry fields (rows, columns,
            spacing_mm, a1_offset_x/y, width_mm, height_mm, ...), or {} on failure.
            This is the single source of truth for plate dimensions - the deck
            canvas renders from it instead of hardcoding geometry.
        """
        try:
            raw  = self._channel.unary_unary(self._rpc("GetLabware"))(b"", timeout=5.0)
            resp = _mp.GetLabware_Responses.FromString(bytes(raw))
            data = yaml.safe_load(resp.Labware.value) or {}
            return data if isinstance(data, dict) else {}
        except Exception as e:
            self.error_occurred.emit(f"fetch_labware: {e}")
            return {}

    def fetch_limits(self) -> tuple[float, float, float, float, float, float] | None:
        """Fetch axis limits as (x_min, x_max, y_min, y_max, z_min, z_max). Returns None on failure."""
        try:
            raw   = self._channel.unary_unary(self._rpc("GetLimits"))(b"", timeout=5.0)
            resp  = _mp.GetLimits_Responses.FromString(bytes(raw))
            parts = [float(v) for v in resp.Limits.value.split("|")]
            if len(parts) == 6:
                return (parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
        except Exception:
            pass
        return None
