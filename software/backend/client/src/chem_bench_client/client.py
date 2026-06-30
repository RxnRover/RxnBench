"""
Blocking Python client for the Chem Bench SiLA servers.

Intended for use in experiment scripts run on the backend machine.

Usage::

    from chem_bench_client import ChemBenchClient

    with ChemBenchClient() as bench:
        bench.load_workspace_yaml(WORKSPACE_YAML)
        bench.set_toolhead("ph_probe")
        bench.confirm_toolhead_mounted()

        results = {}
        for well in ["plate1/A1", "plate1/B1"]:
            bench.move_to_well(well)
            bench.engage_tool()
            results[well] = bench.read_ph()
            bench.disengage_tool()
"""
from __future__ import annotations

import struct

import grpc

from .proto import motion_platform_pb2 as _mp

GANTRY_PORT = 50051
PH_PORT     = 50052

_GANTRY = "sila2.edu.iastate.ames.rxnbench.gantry.v0.Gantry"
_PH     = "sila2.edu.iastate.ames.rxnbench.phsensor.v1.PHSensor"


class ChemBenchClient:
    """Blocking gRPC client for experiment scripts.

    Uses the compiled proto stubs so all field names match the schema
    (Toolheads, Workspaces, Limits, …) without any auto-generated placeholders.
    """

    def __init__(
        self,
        host: str = "localhost",
        gantry_port: int = GANTRY_PORT,
        ph_port: int = PH_PORT,
    ) -> None:
        self._gc = grpc.insecure_channel(f"{host}:{gantry_port}")
        self._pc = grpc.insecure_channel(f"{host}:{ph_port}")

    def close(self) -> None:
        self._gc.close()
        self._pc.close()

    def __enter__(self) -> "ChemBenchClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call(self, method: str, params, timeout: float = 60.0) -> bytes:
        path = f"/{_GANTRY}/{method}"
        raw = self._gc.unary_unary(path)(params.SerializeToString(), timeout=timeout)
        return bytes(raw)

    def _sub_once(self, method: str, params=None, timeout: float = 5.0) -> bytes:
        path = f"/{_GANTRY}/{method}"
        stream = self._gc.unary_stream(path)(
            (params or _mp.Empty()).SerializeToString(), timeout=timeout
        )
        return bytes(next(stream))

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def load_workspace(self, name: str) -> None:
        self._call("SetWorkspace", _mp.SetWorkspace_Parameters(
            name=_mp.SString(value=name)
        ))

    def load_workspace_yaml(self, content: str) -> None:
        self._call("LoadWorkspaceYaml", _mp.LoadWorkspaceYaml_Parameters(
            content=_mp.SString(value=content)
        ))

    def list_workspaces(self) -> list[str]:
        raw  = self._call("ListWorkspaces", _mp.Empty())
        resp = _mp.ListWorkspaces_Responses.FromString(raw)
        return [w for w in resp.Workspaces.value.splitlines() if w]

    # ------------------------------------------------------------------
    # Toolheads
    # ------------------------------------------------------------------

    def set_toolhead(self, name: str) -> None:
        self._call("SetToolhead", _mp.SetToolhead_Parameters(
            name=_mp.SString(value=name)
        ))

    def confirm_toolhead_mounted(self) -> None:
        self._call("ConfirmToolheadMounted", _mp.Empty())

    def clear_toolhead_mounted(self) -> None:
        self._call("ClearToolheadMounted", _mp.Empty())

    def list_toolheads(self) -> list[tuple[str, str]]:
        raw  = self._call("ListToolheads", _mp.Empty())
        resp = _mp.ListToolheads_Responses.FromString(raw)
        return [
            (p[0].strip(), p[1].strip())
            for line in resp.Toolheads.value.splitlines()
            if len(p := line.split("|", 1)) == 2
        ]

    def get_toolhead_z_engage(self) -> float:
        raw  = self._sub_once("Subscribe_ToolheadInfo")
        resp = _mp.Subscribe_ToolheadInfo_Responses.FromString(raw)
        return resp.ToolheadInfo.z_engage.value

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def move_to(self, x: float, y: float, z: float) -> None:
        self._call("MoveTo", _mp.MoveTo_Parameters(
            x=_mp.Real(value=x),
            y=_mp.Real(value=y),
            z=_mp.Real(value=z),
        ))

    def move_to_well(self, label: str) -> None:
        self._call("MoveToWell", _mp.MoveToWell_Parameters(
            label=_mp.SString(value=label)
        ))

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._call("Jog", _mp.Jog_Parameters(
            dx=_mp.Real(value=dx),
            dy=_mp.Real(value=dy),
            dz=_mp.Real(value=dz),
        ))

    def engage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = self.get_toolhead_z_engage()
        self._call("EngageTool", _mp.EngageTool_Parameters(
            depth=_mp.Real(value=depth)
        ))

    def disengage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = self.get_toolhead_z_engage()
        self._call("DisengageTool", _mp.DisengageTool_Parameters(
            depth=_mp.Real(value=depth)
        ))

    def get_position(self) -> tuple[float, float, float]:
        raw  = self._sub_once("Subscribe_Position")
        resp = _mp.Subscribe_Position_Responses.FromString(raw)
        return resp.Position.x.value, resp.Position.y.value, resp.Position.z.value

    def save_and_park(self) -> None:
        self._call("SaveAndPark", _mp.Empty())

    def get_limits(self) -> str:
        raw  = self._call("GetLimits", _mp.Empty())
        resp = _mp.GetLimits_Responses.FromString(raw)
        return resp.Limits.value

    # ------------------------------------------------------------------
    # pH sensor
    # ------------------------------------------------------------------

    def read_ph(self) -> float:
        path   = f"/{_PH}/Subscribe_Ph"
        stream = self._pc.unary_stream(path)(b"", timeout=10.0)
        raw    = bytes(next(stream))
        return _decode_ph(raw)


def _decode_ph(data: bytes) -> float:
    # Subscribe_Ph_Responses { Real Ph = 1; }  —  Real { double value = 1; }
    # Outer: 0x0a (field 1, LEN) + 0x08 (length=8) + inner bytes
    # Inner: 0x09 (field 1, fixed64) + 8 bytes little-endian double
    if len(data) >= 11 and data[0] == 0x0a and data[2] == 0x09:
        return struct.unpack("<d", data[3:11])[0]
    return float("nan")
