"""
SiLA client, raw protobuf codec, and domain types for Chem Bench UI.

Wire-format notes (traced from the unitelabs-sila source):
  Feature RPC package : sila2.edu.iastate.ames.chembench.motionplatform.v0
  Service name        : MotionPlatform
  Subscribe_Position  : unary_stream, empty request, returns Position {x,y,z: Real}
  Subscribe_State     : unary_stream, empty request, returns String state
  UnobservableCommands: unary_unary, empty request  (HomeAuto etc.)
  Jog (Observable)    : unary_unary, Jog_Parameters {Dx,Dy,Dz: Real}  → initiate only
  SiLA Real           : protobuf LEN field; inner field 1 I64 = double
"""

import base64
import dataclasses
import re
import struct
import threading

import grpc
from PySide6.QtCore import QObject, Signal

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


# ── Minimal protobuf encode/decode (no generated stubs needed) ───────────────

def _varint(n: int) -> bytes:
    out = []
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)

def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    n, shift = 0, 0
    while pos < len(buf):
        b = buf[pos]; pos += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, pos
        shift += 7
    return 0, pos

def _len_fields(buf: bytes) -> dict[int, bytes]:
    """Return {field_number: inner_bytes} for every LEN (wire-type 2) field."""
    result: dict[int, bytes] = {}
    pos = 0
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 7
        if wire == 2:
            length, pos = _read_varint(buf, pos)
            result[field] = buf[pos:pos + length]
            pos += length
        elif wire == 0: _, pos = _read_varint(buf, pos)
        elif wire == 1: pos += 8
        elif wire == 5: pos += 4
    return result

def _decode_real(buf: bytes) -> float:
    """Decode a SiLA Real message: inner field 1 is an I64 double."""
    pos = 0
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 7
        if field == 1 and wire == 1:
            return struct.unpack_from('<d', buf, pos)[0]
        if wire == 0: _, pos = _read_varint(buf, pos)
        elif wire == 1: pos += 8
        elif wire == 2:
            length, pos = _read_varint(buf, pos)
            pos += length
        elif wire == 5: pos += 4
    return 0.0

def _decode_position(data: bytes) -> tuple[float, float, float]:
    """Decode Subscribe_Position_Responses → (x, y, z)."""
    outer = _len_fields(data)       # field 1 = Position structure
    if 1 not in outer:
        return 0.0, 0.0, 0.0
    pos_fields = _len_fields(outer[1])   # fields 1,2,3 = x,y,z Real messages
    return (
        _decode_real(pos_fields.get(1, b'')),
        _decode_real(pos_fields.get(2, b'')),
        _decode_real(pos_fields.get(3, b'')),
    )

def _decode_state(data: bytes) -> str:
    """Decode Subscribe_State_Responses → state string."""
    outer = _len_fields(data)
    if 1 not in outer: return ""
    inner = _len_fields(outer[1])
    if 1 not in inner: return ""
    return inner[1].decode("utf-8", errors="replace")

def _encode_real_field(value: float, field_num: int) -> bytes:
    """Encode a SiLA Real as protobuf LEN field N."""
    inner = (b'\x09' + struct.pack('<d', value)) if value != 0.0 else b''
    return _varint((field_num << 3) | 2) + _varint(len(inner)) + inner

def _encode_xyz(x: float, y: float, z: float) -> bytes:
    return _encode_real_field(x, 1) + _encode_real_field(y, 2) + _encode_real_field(z, 3)

def _encode_string_field(value: str, field_num: int) -> bytes:
    """Encode a SiLA String as protobuf LEN field N."""
    utf8 = value.encode("utf-8")
    inner = _varint((1 << 3) | 2) + _varint(len(utf8)) + utf8
    return _varint((field_num << 3) | 2) + _varint(len(inner)) + inner

def _decode_bool(buf: bytes) -> bool:
    """Decode a SiLA Boolean message: inner field 1 is a varint."""
    pos = 0
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 7
        if field == 1 and wire == 0:
            val, pos = _read_varint(buf, pos)
            return bool(val)
        if wire == 0:   _, pos = _read_varint(buf, pos)
        elif wire == 1: pos += 8
        elif wire == 2:
            length, pos = _read_varint(buf, pos); pos += length
        elif wire == 5: pos += 4
    return False

def _decode_string(buf: bytes) -> str:
    """Decode a SiLA String message: inner field 1 is UTF-8 bytes."""
    pos = 0
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 7
        if field == 1 and wire == 2:
            length, pos = _read_varint(buf, pos)
            return buf[pos:pos + length].decode("utf-8", errors="replace")
        if wire == 0:   _, pos = _read_varint(buf, pos)
        elif wire == 1: pos += 8
        elif wire == 2:
            length, pos = _read_varint(buf, pos); pos += length
        elif wire == 5: pos += 4
    return ""


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


def _decode_toolhead_info(data: bytes) -> ToolheadInfo:
    """Decode Subscribe_ToolheadInfo_Responses → ToolheadInfo."""
    outer = _len_fields(data)
    if 1 not in outer:
        return ToolheadInfo()
    f = _len_fields(outer[1])
    return ToolheadInfo(
        active              = _decode_bool(f.get(1, b'')),
        name                = _decode_string(f.get(2, b'')),
        display_name        = _decode_string(f.get(3, b'')),
        footprint_x         = _decode_real(f.get(4, b'')),
        footprint_y         = _decode_real(f.get(5, b'')),
        offset_x            = _decode_real(f.get(6, b'')),
        offset_y            = _decode_real(f.get(7, b'')),
        tip_offset_z        = _decode_real(f.get(8, b'')),
        z_engage            = _decode_real(f.get(9, b'')),
        tip_x               = _decode_real(f.get(10, b'')),
        tip_y               = _decode_real(f.get(11, b'')),
        requires_manual_z   = _decode_bool(f.get(12, b'')),
        requires_manual_homing = _decode_bool(f.get(13, b'')),
        toolhead_mounted    = _decode_bool(f.get(14, b'')),
    )


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
                    x, y, z = _decode_position(bytes(msg))
                    self.position_updated.emit(x, y, z)
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
                    self.state_updated.emit(_decode_state(bytes(msg)))
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
                    self.toolhead_updated.emit(_decode_toolhead_info(bytes(msg)))
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
                    f = _len_fields(bytes(msg))
                    inner = _len_fields(f.get(1, b''))
                    val = bool(inner.get(1, b'\x00')[0]) if inner.get(1) else False
                    self.saved_state_updated.emit(val)
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
    def set_toolhead(self, name: str):
        self._fire("SetToolhead", _encode_string_field(name, 1))
    def clear_toolhead(self):         self._fire("ClearToolhead")
    def confirm_toolhead_mounted(self): self._fire("ConfirmToolheadMounted")
    def clear_toolhead_mounted(self):   self._fire("ClearToolheadMounted")
    def save_and_park(self):            self._fire("SaveAndPark")

    def fetch_toolhead_list(self) -> list[tuple[str, str]]:
        """Blocking call — run in a thread. Returns [(name, display_name), ...]."""
        try:
            raw = self._channel.unary_unary(self._method("ListToolheads"))(b"", timeout=5.0)
            text = _decode_string(_len_fields(bytes(raw)).get(1, b''))
            result = []
            for line in text.splitlines():
                parts = line.split("|", 1)
                if len(parts) == 2:
                    result.append((parts[0].strip(), parts[1].strip()))
            return result
        except Exception as e:
            self.error_occurred.emit(f"fetch_toolhead_list: {e}")
            return []

    def confirm_x_min(self):       self._fire("ConfirmXMin")
    def confirm_x_max(self):       self._fire("ConfirmXMax")
    def confirm_y_min(self):       self._fire("ConfirmYMin")
    def confirm_y_max(self):       self._fire("ConfirmYMax")
    def confirm_z_reference(self): self._fire("ConfirmZReference")

    def jog(self, dx=0.0, dy=0.0, dz=0.0):
        # Jog is ObservableCommand — calling Jog initiates it; result stream ignored
        self._fire("Jog", _encode_xyz(dx, dy, dz))

    def move_to(self, x: float, y: float, z: float):
        self._fire("MoveTo", _encode_xyz(x, y, z))
