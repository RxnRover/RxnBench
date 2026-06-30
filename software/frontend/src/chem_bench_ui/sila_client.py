"""
SiLA client for Chem Bench UI.

Uses grpcio-tools-generated stubs from the proto/ package for all
serialization. Field numbers are structurally guaranteed to match the
CDK wire format because gen_proto.py derives them from the same
dataclasses.fields() source the CDK runtime uses.

Regenerate stubs when backend dataclasses change:
    cd software/backend
    uv run python scripts/gen_proto.py \\
        > ../frontend/src/chem_bench_ui/proto/motion_platform.proto
    python -m grpc_tools.protoc \\
        -I ../frontend/src/chem_bench_ui/proto \\
        --python_out=../frontend/src/chem_bench_ui/proto \\
        ../frontend/src/chem_bench_ui/proto/motion_platform.proto
"""

import base64
import dataclasses
import re
import threading
from typing import Callable

import grpc
from PySide6.QtCore import QObject, Signal

from .proto import motion_platform_pb2 as _mp
from .proto import sila_service_pb2 as _ss

SILA_PORT = 50051

_PKG = "sila2.edu.iastate.ames.rxnbench.gantry.v0"
_SVC = "Gantry"

_SS_PKG = "sila2.org.silastandard.core.silaservice.v1"
_SS_SVC = "SiLAService"


@dataclasses.dataclass(frozen=True)
class FeatureDescriptor:
    """Maps a server-reported feature identifier to a UI display name.

    'identifier' is the fully-qualified SiLA2 feature identifier returned by
    SiLAService.GetImplementedFeatures, e.g. 'edu.iastate.ames/rxnbench/MotionPlatform/v0'.
    The rpc_package form is: sila2.<originator>.<category>.<feature_lower>.v<major>.

    'start_streams' is called once after discovery is confirmed for this generation.
    Signature: (client: SilaClient, gen: int) -> None
    """
    name: str        # UI label used by MainWindow to select the right tab builder
    identifier: str  # Fully-qualified feature identifier (case-insensitive match)
    start_streams: Callable[["SilaClient", int], None]


def _start_motion_streams(client: "SilaClient", gen: int) -> None:
    """Start the four Motion Platform subscription threads for this connection generation."""
    threading.Thread(target=client._stream_position,    args=(gen,), daemon=True).start()
    threading.Thread(target=client._stream_state,       args=(gen,), daemon=True).start()
    threading.Thread(target=client._stream_toolhead,    args=(gen,), daemon=True).start()
    threading.Thread(target=client._stream_saved_state, args=(gen,), daemon=True).start()


_FEATURE_REGISTRY: list[FeatureDescriptor] = [
    FeatureDescriptor(
        name="Gantry",
        identifier="edu.iastate.ames/rxnbench/Gantry/v0",
        start_streams=_start_motion_streams,
    ),
    # FeatureDescriptor(
    #     name="pH Sensor",
    #     identifier="edu.iastate.ames/rxnbench/PHSensor/v0",
    #     start_streams=_start_ph_streams,
    # ),
]


@dataclasses.dataclass
class ToolheadInfo:
    """Current toolhead geometry received from the SiLA toolhead_info property."""
    active: bool = False
    name: str = ""
    display_name: str = ""
    footprint_x: float = 0.0
    footprint_y: float = 0.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    tip_offset_z: float = 0.0
    z_engage: float = 0.0
    tip_x: float = 0.0
    tip_y: float = 0.0
    toolhead_mounted: bool = False


class SilaClient(QObject):
    """Connects to the SiLA server, discovers features, and exposes commands as Qt signals."""
    position_updated    = Signal(float, float, float)
    state_updated       = Signal(str)
    connection_changed  = Signal(bool)    # True = gRPC channel READY
    error_occurred      = Signal(str)
    toolhead_updated    = Signal(object)  # emits ToolheadInfo
    features_discovered = Signal(list)    # emits list[str] of found feature names
    feature_state_changed = Signal(str, bool)  # (feature name, streams ok)
    saved_state_updated = Signal(bool)    # True = saved homing state loaded on server
    limits_updated      = Signal(float, float, float, float, float, float)  # x_min,x_max,y_min,y_max,z_min,z_max

    def __init__(self):
        super().__init__()
        self._channel: grpc.Channel | None = None
        self._stop = threading.Event()
        self._host = ""
        # Incremented on each connect_to(); stream threads exit when self._gen no longer
        # matches, ensuring only one active set of threads per connection.
        self._gen: int = 0

    @property
    def host(self) -> str:
        return self._host

    def connect_to(self, host: str, port: int = SILA_PORT):
        self._stop.set()
        if self._channel:
            self._channel.close()

        self._host = host
        self._gen += 1
        my_gen = self._gen
        self._stop = threading.Event()
        self._channel = grpc.insecure_channel(f"{host}:{port}")

        # Subscribe to the gRPC channel state machine so the indicator dot
        # reflects TCP connectivity before any stream data arrives.
        _stop_ref = self._stop
        def _on_channel_state(connectivity):
            if not _stop_ref.is_set():
                self.connection_changed.emit(
                    connectivity == grpc.ChannelConnectivity.READY
                )
        self._channel.subscribe(_on_channel_state, try_to_connect=True)

        threading.Thread(target=self._discover_and_stream, args=(my_gen,), daemon=True).start()

    def disconnect(self):
        self._stop.set()

    def _fetch_implemented_features(self) -> list[str]:
        """Call SiLAService.GetImplementedFeatures; return list of feature identifier strings."""
        path = f"/{_SS_PKG}.{_SS_SVC}/Get_ImplementedFeatures"
        try:
            raw = self._channel.unary_unary(path)(b"", timeout=5.0)
            resp = _ss.Get_ImplementedFeatures_Responses.FromString(bytes(raw))
            return [item.value for item in resp.ImplementedFeatures]
        except Exception:
            return []

    def _discover_and_stream(self, gen: int):
        """Ask the server what features it implements, filter through registry, start streams."""
        server_ids = self._fetch_implemented_features()
        found_descs: list[FeatureDescriptor] = [
            fd for fd in _FEATURE_REGISTRY
            if any(sid.lower() == fd.identifier.lower() for sid in server_ids)
        ]
        found = [fd.name for fd in found_descs]

        self.features_discovered.emit(found)

        if self._gen != gen:
            return

        for fd in found_descs:
            if self._gen == gen:  # re-check per feature in case of rapid reconnect
                fd.start_streams(self, gen)

        if self._gen == gen and any(sid.lower() == _FEATURE_REGISTRY[0].identifier.lower()
                                    for sid in server_ids):
            limits = self.fetch_limits()
            if limits is not None:
                self.limits_updated.emit(*limits)

    def _method(self, name: str) -> str:
        return f"/{_PKG}.{_SVC}/{name}"

    def _stream_position(self, gen: int):
        while self._gen == gen and not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_Position"))
                first = True
                for msg in call(b""):
                    if self._gen != gen or self._stop.is_set():
                        return
                    if first:
                        self.feature_state_changed.emit("Gantry", True)
                        first = False
                    resp = _mp.Subscribe_Position_Responses.FromString(bytes(msg))
                    self.position_updated.emit(
                        resp.Position.x.value,
                        resp.Position.y.value,
                        resp.Position.z.value,
                    )
            except Exception:
                self.feature_state_changed.emit("Gantry", False)
                if self._gen != gen or self._stop.wait(3.0):
                    return

    def _stream_state(self, gen: int):
        while self._gen == gen and not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_State"))
                for msg in call(b""):
                    if self._gen != gen or self._stop.is_set():
                        return
                    resp = _mp.Subscribe_State_Responses.FromString(bytes(msg))
                    self.state_updated.emit(resp.State.value)
            except Exception:
                if self._gen != gen or self._stop.wait(3.0):
                    return

    def _stream_toolhead(self, gen: int):
        while self._gen == gen and not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_ToolheadInfo"))
                for msg in call(b""):
                    if self._gen != gen or self._stop.is_set():
                        return
                    resp = _mp.Subscribe_ToolheadInfo_Responses.FromString(bytes(msg))
                    th = resp.ToolheadInfo
                    self.toolhead_updated.emit(ToolheadInfo(
                        active              = th.active.value,
                        name                = th.name.value,
                        display_name        = th.display_name.value,
                        footprint_x         = th.footprint_x.value,
                        footprint_y         = th.footprint_y.value,
                        offset_x            = th.offset_x.value,
                        offset_y            = th.offset_y.value,
                        tip_offset_z        = th.tip_offset_z.value,
                        z_engage            = th.z_engage.value,
                        tip_x               = th.tip_x.value,
                        tip_y               = th.tip_y.value,
                        toolhead_mounted    = th.toolhead_mounted.value,
                    ))
            except Exception:
                if self._gen != gen or self._stop.wait(3.0):
                    return

    def _stream_saved_state(self, gen: int):
        while self._gen == gen and not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_HasSavedState"))
                for msg in call(b""):
                    if self._gen != gen or self._stop.is_set():
                        return
                    resp = _mp.Subscribe_HasSavedState_Responses.FromString(bytes(msg))
                    self.saved_state_updated.emit(resp.HasSavedState.value)
            except Exception:
                if self._gen != gen or self._stop.wait(5.0):
                    return

    @staticmethod
    def _format_error(method: str, exc: Exception) -> str:
        raw = str(exc)
        # gRPC error details are base64-encoded proto; decode to extract the human-readable message
        m = re.search(r'details\s*=\s*"([A-Za-z0-9+/=]{20,})"', raw)
        if m:
            try:
                decoded = base64.b64decode(m.group(1)).decode("utf-8", errors="replace")
                for marker in ("HTTPError:", "ValueError:", "MotionLimitError:", "Error:"):
                    if marker in decoded:
                        return decoded[decoded.index(marker):].split("\n")[0][:150]
                return decoded[:150]
            except Exception:
                pass
        m2 = re.search(r'details\s*=\s*"([^"]{1,150})"', raw)
        if m2:
            return m2.group(1)
        return f"{method} failed"

    def _call(self, method: str, request: bytes = b""):
        try:
            self._channel.unary_unary(self._method(method))(request)
        except Exception as e:
            print(f"[SiLA] {method} error: {e}")
            self.error_occurred.emit(self._format_error(method, e))

    def _fire(self, method: str, request: bytes = b""):
        threading.Thread(target=self._call, args=(method, request), daemon=True).start()

    def start_manual_homing(self):    self._fire("StartManualHoming")
    def finish_homing(self):          self._fire("FinishHoming")
    def clear_toolhead(self):         self._fire("ClearToolhead")
    def confirm_toolhead_mounted(self): self._fire("ConfirmToolheadMounted")
    def clear_toolhead_mounted(self):   self._fire("ClearToolheadMounted")
    def save_and_park(self):            self._fire("SaveAndPark")
    def confirm_x_min(self):            self._fire("ConfirmXMin")
    def confirm_x_max(self):            self._fire("ConfirmXMax")
    def confirm_y_min(self):            self._fire("ConfirmYMin")
    def confirm_y_max(self):            self._fire("ConfirmYMax")
    def confirm_z_reference(self):      self._fire("ConfirmZReference")

    def set_toolhead(self, name: str):
        params = _mp.SetToolhead_Parameters()
        params.name.value = name
        self._fire("SetToolhead", params.SerializeToString())

    def jog(self, dx=0.0, dy=0.0, dz=0.0):
        params = _mp.Jog_Parameters()
        params.dx.value = dx
        params.dy.value = dy
        params.dz.value = dz
        self._fire("Jog", params.SerializeToString())

    def move_to(self, x: float, y: float, z: float):
        params = _mp.MoveTo_Parameters()
        params.x.value = x
        params.y.value = y
        params.z.value = z
        self._fire("MoveTo", params.SerializeToString())

    def fetch_toolhead_list(self) -> list[tuple[str, str]]:
        """Blocking call - run in a thread. Returns [(name, display_name), ...]."""
        try:
            raw = self._channel.unary_unary(self._method("ListToolheads"))(b"", timeout=5.0)
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

    def set_workspace(self, name: str):
        params = _mp.SetWorkspace_Parameters()
        params.name.value = name
        self._fire("SetWorkspace", params.SerializeToString())

    def move_to_well(self, label: str):
        params = _mp.MoveToWell_Parameters()
        params.label.value = label
        self._fire("MoveToWell", params.SerializeToString())

    def fetch_workspace_list(self) -> list[str]:
        """Blocking call - run in a thread. Returns list of workspace names."""
        try:
            raw = self._channel.unary_unary(self._method("ListWorkspaces"))(b"", timeout=5.0)
            resp = _mp.ListWorkspaces_Responses.FromString(bytes(raw))
            return [w for w in resp.Workspaces.value.splitlines() if w]
        except Exception as e:
            self.error_occurred.emit(f"fetch_workspace_list: {e}")
            return []

    def fetch_limits(self) -> tuple[float, float, float, float, float, float] | None:
        """Blocking call - fetch calibrated axis limits from the server.

        Returns (x_min, x_max, y_min, y_max, z_min, z_max) or None on error.
        Call at connection time to cache limits for the session.
        """
        try:
            raw = self._channel.unary_unary(self._method("GetLimits"))(b"", timeout=5.0)
            resp = _mp.GetLimits_Responses.FromString(bytes(raw))
            parts = [float(v) for v in resp.Limits.value.split("|")]
            if len(parts) == 6:
                return (parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
        except Exception:
            pass
        return None
