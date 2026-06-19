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

import grpc
from PySide6.QtCore import QObject, Signal

from .proto import motion_platform_pb2 as _mp

# ── Machine limits (SV08 defaults) ──────────────────────────────────────────
X_MAX, Y_MAX, Z_MAX = 350.0, 350.0, 340.0
SILA_PORT = 50051

# ── SiLA feature constants ───────────────────────────────────────────────────
_PKG = "sila2.edu.iastate.ames.chembench.motionplatform.v0"
_SVC = "MotionPlatform"

# Registry of every feature the desktop knows about.
# "probe" is a lightweight unary method used to detect presence.
_KNOWN_FEATURES: list[dict] = [
    {
        "name": "Motion Platform",
        "pkg":  _PKG,
        "svc":  _SVC,
        "probe": "ListToolheads",
    },
    # Future features go here:
    # {"name": "pH Probe", "pkg": "...", "svc": "PHProbe", "probe": "GetStatus"},
]


# ── Domain types ─────────────────────────────────────────────────────────────

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
    requires_manual_z: bool = True
    requires_manual_homing: bool = False
    toolhead_mounted: bool = False


# ── SiLA client ──────────────────────────────────────────────────────────────

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

    def __init__(self):
        super().__init__()
        self._channel: grpc.Channel | None = None
        self._stop = threading.Event()
        self._host = ""

    def connect_to(self, host: str, port: int = SILA_PORT):
        self._stop.set()
        if self._channel:
            self._channel.close()

        self._host = host
        self._stop = threading.Event()
        self._channel = grpc.insecure_channel(f"{host}:{port}")

        # Emit connection_changed directly from the gRPC channel state machine so
        # the indicator dot turns green as soon as the TCP handshake succeeds —
        # regardless of whether any stream data has arrived yet.
        _stop_ref = self._stop
        def _on_channel_state(connectivity):
            if not _stop_ref.is_set():
                self.connection_changed.emit(
                    connectivity == grpc.ChannelConnectivity.READY
                )
        self._channel.subscribe(_on_channel_state, try_to_connect=True)

        # Probe features first, then start streams for the ones that exist.
        threading.Thread(target=self._discover_and_stream, daemon=True).start()

    def disconnect(self):
        self._stop.set()

    # ── Feature discovery ──────────────────────────────────────────────────

    def _discover_and_stream(self):
        """Probe every known feature and emit features_discovered, then start streams."""
        found: list[str] = []
        for feat in _KNOWN_FEATURES:
            if self._probe_feature(feat["pkg"], feat["svc"], feat["probe"]):
                found.append(feat["name"])

        self.features_discovered.emit(found)

        if "Motion Platform" in found:
            threading.Thread(target=self._stream_position,    daemon=True).start()
            threading.Thread(target=self._stream_state,       daemon=True).start()
            threading.Thread(target=self._stream_toolhead,    daemon=True).start()
            threading.Thread(target=self._stream_saved_state, daemon=True).start()

    def _probe_feature(self, pkg: str, svc: str, method: str) -> bool:
        """Return True if the gRPC service is reachable (even if the call itself errors)."""
        full = f"/{pkg}.{svc}/{method}"
        try:
            self._channel.unary_unary(full)(b"", timeout=4.0)
            return True
        except grpc.RpcError as e:
            # Any response other than UNAVAILABLE means the service is there.
            return e.code() != grpc.StatusCode.UNAVAILABLE
        except Exception:
            return False

    # ── Subscription streams ───────────────────────────────────────────────

    def _method(self, name: str) -> str:
        return f"/{_PKG}.{_SVC}/{name}"

    def _stream_position(self):
        while not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_Position"))
                first = True
                for msg in call(b""):
                    if self._stop.is_set():
                        return
                    if first:
                        self.feature_state_changed.emit("Motion Platform", True)
                        first = False
                    resp = _mp.Subscribe_Position_Responses.FromString(bytes(msg))
                    self.position_updated.emit(
                        resp.Position.x.value,
                        resp.Position.y.value,
                        resp.Position.z.value,
                    )
            except Exception:
                self.feature_state_changed.emit("Motion Platform", False)
                if not self._stop.wait(3.0):
                    continue

    def _stream_state(self):
        while not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_State"))
                for msg in call(b""):
                    if self._stop.is_set():
                        return
                    resp = _mp.Subscribe_State_Responses.FromString(bytes(msg))
                    self.state_updated.emit(resp.State.value)
            except Exception:
                if not self._stop.wait(3.0):
                    continue

    def _stream_toolhead(self):
        while not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_ToolheadInfo"))
                for msg in call(b""):
                    if self._stop.is_set():
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
                        requires_manual_z   = th.requires_manual_z.value,
                        requires_manual_homing = th.requires_manual_homing.value,
                        toolhead_mounted    = th.toolhead_mounted.value,
                    ))
            except Exception:
                if not self._stop.wait(3.0):
                    continue

    def _stream_saved_state(self):
        while not self._stop.is_set():
            try:
                call = self._channel.unary_stream(self._method("Subscribe_HasSavedState"))
                for msg in call(b""):
                    if self._stop.is_set():
                        return
                    resp = _mp.Subscribe_HasSavedState_Responses.FromString(bytes(msg))
                    self.saved_state_updated.emit(resp.HasSavedState.value)
            except Exception:
                if not self._stop.wait(5.0):
                    continue

    @staticmethod
    def _format_error(method: str, exc: Exception) -> str:
        raw = str(exc)
        # SiLA/Moonraker errors arrive as base64-encoded proto in the gRPC details field
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

    # ── Commands ──

    def home_auto(self):              self._fire("HomeAuto")
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
        """Blocking call — run in a thread. Returns [(name, display_name), ...]."""
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
