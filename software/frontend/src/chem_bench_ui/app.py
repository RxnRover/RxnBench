"""
Automated Chem Bench — Desktop Control UI

Connects to the SiLA server (port 50051) running on the RPi or laptop.
Uses raw gRPC with hand-encoded protobuf — no generated stubs needed.

Wire-format notes (traced from the unitelabs-sila source):
  Feature RPC package : sila2.edu.iastate.ames.chembench.motionplatform.v0
  Service name        : MotionPlatform
  Subscribe_Position  : unary_stream, empty request, returns Position {x,y,z: Real}
  Subscribe_State     : unary_stream, empty request, returns String state
  UnobservableCommands: unary_unary, empty request  (HomeAuto etc.)
  Jog (Observable)    : unary_unary, Jog_Parameters {Dx,Dy,Dz: Real}  → initiate only
  SiLA Real           : protobuf LEN field; inner field 1 I64 = double

Author: John Brittain
Date: Jun 18 2026
"""

import base64
import dataclasses
import re
import struct
import threading
import sys

import grpc
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QDoubleValidator
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QGroupBox, QGridLayout, QButtonGroup,
    QComboBox, QListWidget, QTabWidget, QSplitter,
)

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


def _decode_toolhead_info(data: bytes) -> ToolheadInfo:
    """Decode Subscribe_ToolheadInfo_Responses → ToolheadInfo."""
    outer = _len_fields(data)
    if 1 not in outer:
        return ToolheadInfo()
    f = _len_fields(outer[1])
    return ToolheadInfo(
        active       = _decode_bool(f.get(1, b'')),
        name         = _decode_string(f.get(2, b'')),
        display_name = _decode_string(f.get(3, b'')),
        footprint_x  = _decode_real(f.get(4, b'')),
        footprint_y  = _decode_real(f.get(5, b'')),
        offset_x     = _decode_real(f.get(6, b'')),
        offset_y     = _decode_real(f.get(7, b'')),
        tip_offset_z = _decode_real(f.get(8, b'')),
        z_engage     = _decode_real(f.get(9, b'')),
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
            threading.Thread(target=self._stream_position, daemon=True).start()
            threading.Thread(target=self._stream_state,    daemon=True).start()
            threading.Thread(target=self._stream_toolhead, daemon=True).start()

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
    def home_auto(self):           self._fire("HomeAuto")
    def start_manual_homing(self): self._fire("StartManualHoming")
    def finish_homing(self):       self._fire("FinishHoming")
    def set_toolhead(self, name: str):
        self._fire("SetToolhead", _encode_string_field(name, 1))
    def clear_toolhead(self):      self._fire("ClearToolhead")

    def fetch_toolhead_list(self) -> list[tuple[str, str]]:
        """Blocking call — run in a thread. Returns [(name, display_name), ...]."""
        try:
            raw = self._channel.unary_unary(self._method("ListToolheads"))(b"")
            text = _decode_string(_len_fields(bytes(raw)).get(1, b''))
            result = []
            for line in text.splitlines():
                parts = line.split("|", 1)
                if len(parts) == 2:
                    result.append((parts[0].strip(), parts[1].strip()))
            return result
        except Exception:
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


# ── Position grid widget ──────────────────────────────────────────────────────

class PositionGrid(QWidget):
    """Top-down XY view of the build plate. Click to send a move_to command."""

    move_requested = Signal(float, float)

    def __init__(self):
        super().__init__()
        self._x = self._y = 0.0
        self._target_x: float | None = None
        self._target_y: float | None = None
        self._homed = False
        self._toolhead: ToolheadInfo | None = None
        self.setMinimumSize(260, 260)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_position(self, x: float, y: float, homed: bool = False):
        self._x, self._y, self._homed = x, y, homed
        if self._target_x is not None:
            if abs(x - self._target_x) < 1.0 and abs(y - self._target_y) < 1.0:
                self._target_x = self._target_y = None
        self.update()

    def set_toolhead(self, info: "ToolheadInfo | None"):
        self._toolhead = info
        self.update()

    def _to_machine(self, px: float, py: float) -> tuple[float, float]:
        pad = 24
        area_w = self.width() - 2 * pad
        area_h = self.height() - 2 * pad
        x = (px - pad) / area_w * X_MAX
        y = (area_h - (py - pad)) / area_h * Y_MAX
        return max(0.0, min(X_MAX, x)), max(0.0, min(Y_MAX, y))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = self._to_machine(event.position().x(), event.position().y())
            self._target_x, self._target_y = x, y
            self.update()
            self.move_requested.emit(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 24

        area_w = w - 2 * pad
        area_h = h - 2 * pad

        # Grid background
        p.fillRect(pad, pad, area_w, area_h, QColor("#0f1117"))
        p.setPen(QPen(QColor("#1e2130"), 1))
        for i in range(6):
            gx = pad + int(area_w * i / 5)
            gy = pad + int(area_h * i / 5)
            p.drawLine(gx, pad, gx, pad + area_h)
            p.drawLine(pad, gy, pad + area_w, gy)

        # Border
        p.setPen(QPen(QColor("#3a3a5c"), 1))
        p.drawRect(pad, pad, area_w, area_h)

        # Gantry structure (top-down view)
        cy_g = int(pad + area_h - (self._y / Y_MAX) * area_h)
        # Y linear rails — two vertical bars on the left and right frame edges
        p.setPen(QPen(QColor("#252840"), 4))
        p.drawLine(pad, pad, pad, pad + area_h)
        p.drawLine(pad + area_w, pad, pad + area_w, pad + area_h)
        # X gantry beam — horizontal bar at current Y spanning the full X rail
        p.setPen(QPen(QColor("#2a3258"), 2))
        p.drawLine(pad, cy_g, pad + area_w, cy_g)
        # Carriage blocks (where the gantry rides on the Y rails)
        bw, bh = 8, 14
        p.setBrush(QBrush(QColor("#3a4570")))
        p.setPen(QPen(QColor("#5060a0"), 1))
        p.drawRect(pad - bw // 2, cy_g - bh // 2, bw, bh)
        p.drawRect(pad + area_w - bw // 2, cy_g - bh // 2, bw, bh)

        # Axis labels
        p.setPen(QColor("#555"))
        p.setFont(QFont("monospace", 8))
        p.drawText(pad, h - 6, "0")
        p.drawText(w - 36, h - 6, f"{X_MAX:.0f}")
        p.drawText(2, pad + 10, f"{Y_MAX:.0f}")
        p.drawText(2, h - pad - 2, "0")
        p.drawText(w // 2 - 6, h - 6, "X")
        p.drawText(2, h // 2, "Y")

        # Toolhead footprint rectangle
        th = self._toolhead
        if th and th.active and th.footprint_x > 0 and th.footprint_y > 0:
            fp_w = (th.footprint_x / X_MAX) * area_w
            fp_h = (th.footprint_y / Y_MAX) * area_h
            cx0  = pad + (self._x / X_MAX) * area_w
            cy0  = pad + area_h - (self._y / Y_MAX) * area_h
            fx   = int(cx0 - fp_w / 2)
            fy   = int(cy0 - fp_h / 2)
            # Semi-transparent fill
            fill = QColor("#7c4dff")
            fill.setAlpha(40)
            p.fillRect(fx, fy, int(fp_w), int(fp_h), fill)
            # Border
            p.setPen(QPen(QColor("#7c4dff"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(fx, fy, int(fp_w), int(fp_h))
            # Tool centre (carriage + XY offset)
            tcx = int(cx0 + (th.offset_x / X_MAX) * area_w)
            tcy = int(cy0 - (th.offset_y / Y_MAX) * area_h)
            p.setPen(QPen(QColor("#ce93d8"), 1))
            arm = 5
            p.drawLine(tcx - arm, tcy, tcx + arm, tcy)
            p.drawLine(tcx, tcy - arm, tcx, tcy + arm)

        # Target crosshair (click-to-move destination)
        if self._target_x is not None:
            tx = int(pad + (self._target_x / X_MAX) * area_w)
            ty = int(pad + area_h - (self._target_y / Y_MAX) * area_h)
            p.setPen(QPen(QColor("#29b6f6"), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(tx - 9, ty - 9, 18, 18)
            p.setPen(QPen(QColor("#29b6f6"), 1))
            p.drawLine(tx - 14, ty, tx - 6, ty)
            p.drawLine(tx + 6,  ty, tx + 14, ty)
            p.drawLine(tx, ty - 14, tx, ty - 6)
            p.drawLine(tx, ty + 6,  tx, ty + 14)

        # Carriage dot — Y=0 at front/bottom, increases toward back/top
        cx = pad + (self._x / X_MAX) * area_w
        cy = pad + area_h - (self._y / Y_MAX) * area_h

        # Drop shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 80)))
        p.drawEllipse(int(cx) - 6, int(cy) - 4, 12, 12)

        color = QColor("#00e676") if self._homed else QColor("#ff9800")
        p.setBrush(QBrush(color))
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.drawEllipse(int(cx) - 5, int(cy) - 5, 10, 10)
        p.end()


# ── Z-axis bar ───────────────────────────────────────────────────────────────

class ZBar(QWidget):
    """Vertical indicator showing current Z height from 0 (bed) to Z_MAX (fully raised)."""

    def __init__(self):
        super().__init__()
        self._z = 0.0
        self._homed = False
        self._toolhead: ToolheadInfo | None = None
        self.setFixedWidth(52)
        self.setMinimumHeight(260)

    def set_z(self, z: float, homed: bool = False):
        self._z, self._homed = z, homed
        self.update()

    def set_toolhead(self, info: "ToolheadInfo | None"):
        self._toolhead = info
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 24
        track_top = pad
        track_bot = h - pad
        track_h   = track_bot - track_top
        track_x   = w // 2 - 6
        track_w   = 12

        # Track background
        p.fillRect(track_x, track_top, track_w, track_h, QColor("#0f1117"))
        p.setPen(QPen(QColor("#3a3a5c"), 1))
        p.drawRect(track_x, track_top, track_w, track_h)

        # Filled portion (bottom = Z=0, top = Z_MAX)
        frac   = max(0.0, min(1.0, self._z / Z_MAX)) if Z_MAX > 0 else 0.0
        fill_h = int(frac * track_h)
        fill_y = track_bot - fill_h
        color  = QColor("#7c4dff") if self._homed else QColor("#ff9800")
        if fill_h > 0:
            p.fillRect(track_x + 1, fill_y, track_w - 2, fill_h, color)

        # Marker line at current Z
        p.setPen(QPen(color.lighter(160), 2))
        p.drawLine(track_x - 3, fill_y, track_x + track_w + 3, fill_y)

        # Tick marks at 25 % intervals
        p.setPen(QPen(QColor("#2a2d3e"), 1))
        for frac_tick in (0.25, 0.5, 0.75):
            ty = int(track_bot - frac_tick * track_h)
            p.drawLine(track_x, ty, track_x + track_w, ty)

        # End labels
        p.setFont(QFont("monospace", 8))
        p.setPen(QColor("#555"))
        p.drawText(0, track_top - 2, w, 12, Qt.AlignmentFlag.AlignHCenter, f"{Z_MAX:.0f}")
        p.drawText(0, track_bot + 2, w, 12, Qt.AlignmentFlag.AlignHCenter, "0")

        # Axis label
        p.setPen(QColor("#666"))
        p.setFont(QFont("monospace", 9))
        p.drawText(0, h // 2 - 6, w, 12, Qt.AlignmentFlag.AlignHCenter, "Z")

        # Current value floating near the marker (clamped to stay in view)
        p.setPen(QColor("#dde1ec"))
        p.setFont(QFont("monospace", 8))
        val_y = max(track_top + 12, min(fill_y - 2, track_bot - 12))
        p.drawText(0, val_y, w, 12, Qt.AlignmentFlag.AlignHCenter, f"{self._z:.1f}")

        # Toolhead tip and engage depth markers
        th = self._toolhead
        if th and th.active and th.tip_offset_z > 0:
            tip_z  = self._z - th.tip_offset_z
            tip_y  = int(track_bot - (tip_z / Z_MAX) * track_h)
            # Tip line — amber
            p.setPen(QPen(QColor("#ffb300"), 2))
            p.drawLine(track_x - 4, tip_y, track_x + track_w + 4, tip_y)
            if th.z_engage > 0:
                eng_z = tip_z - th.z_engage
                eng_y = int(track_bot - (eng_z / Z_MAX) * track_h)
                # Engage bracket — dashed red
                pen = QPen(QColor("#ef5350"), 1, Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawLine(track_x + track_w + 4, tip_y,
                           track_x + track_w + 4, eng_y)
                p.setPen(QPen(QColor("#ef5350"), 2))
                p.drawLine(track_x - 4, eng_y, track_x + track_w + 4, eng_y)

        p.end()


# ── Toolhead panel ───────────────────────────────────────────────────────────

class ToolheadPanel(QGroupBox):
    """Shows the active toolhead; dropdown populated from the server's installed configs."""

    def __init__(self, client: SilaClient):
        super().__init__("Toolhead")
        self._client = client
        self._names: list[str] = []   # parallel to combo items
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(4)

        self._active_lbl = QLabel("None")
        self._active_lbl.setStyleSheet("font-size:11px; color:#555;")
        vbox.addWidget(self._active_lbl)

        # Dropdown + refresh
        row1 = QHBoxLayout()
        self._combo = QComboBox()
        self._combo.setPlaceholderText("select toolhead…")
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        row1.addWidget(self._combo, 1)
        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Refresh toolhead list from server")
        self._refresh_btn.clicked.connect(self._refresh)
        row1.addWidget(self._refresh_btn)
        vbox.addLayout(row1)

        # Set / Clear
        row2 = QHBoxLayout()
        set_btn = QPushButton("Set")
        set_btn.setStyleSheet("background:#1565c0; color:white; font-size:11px;")
        set_btn.clicked.connect(self._set)
        row2.addWidget(set_btn)
        clr_btn = QPushButton("Clear")
        clr_btn.setStyleSheet("color:#666; font-size:11px;")
        clr_btn.clicked.connect(self._clear)
        row2.addWidget(clr_btn)
        vbox.addLayout(row2)

    def update_info(self, info: ToolheadInfo):
        if info.active:
            label = info.display_name or info.name
            self._active_lbl.setText(label)
            self._active_lbl.setStyleSheet("font-size:11px; color:#ce93d8;")
        else:
            self._active_lbl.setText("None")
            self._active_lbl.setStyleSheet("font-size:11px; color:#555;")

    def _refresh(self):
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("…")
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        entries = self._client.fetch_toolhead_list()
        # Update UI on main thread via a zero-delay timer trick
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._populate(entries))

    def _populate(self, entries: list[tuple[str, str]]):
        self._combo.clear()
        self._names = []
        for name, display in entries:
            self._combo.addItem(display)
            self._names.append(name)
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↻")

    def _set(self):
        idx = self._combo.currentIndex()
        if 0 <= idx < len(self._names):
            self._client.set_toolhead(self._names[idx])

    def _clear(self):
        self._client.clear_toolhead()

    def update_client(self, client: SilaClient):
        self._client = client
        self._refresh()   # auto-populate on reconnect


# ── Toolhead manager panel (full tab) ────────────────────────────────────────

class ToolheadManagerPanel(QWidget):
    """Dedicated tab for browsing installed toolheads and setting the active one.

    Left column: list of all toolheads on the server.
    Right column: details of the selected/active toolhead.
    """

    def __init__(self, client: SilaClient):
        super().__init__()
        self._client = client
        self._names: list[str] = []
        self._active_info = ToolheadInfo()
        self._build()

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setSpacing(12)
        outer.setContentsMargins(8, 8, 8, 8)

        # ── Left: active banner + list ─────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(6)

        active_box = QGroupBox("Active Toolhead")
        al = QVBoxLayout(active_box)
        self._active_lbl = QLabel("None")
        self._active_lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#555;")
        al.addWidget(self._active_lbl)
        clr_btn = QPushButton("Clear Active")
        clr_btn.setStyleSheet("color:#888;")
        clr_btn.clicked.connect(lambda: self._client.clear_toolhead())
        al.addWidget(clr_btn)
        left.addWidget(active_box)

        list_box = QGroupBox("Installed Toolheads")
        ll = QVBoxLayout(list_box)
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_selection)
        ll.addWidget(self._list, 1)

        btns = QHBoxLayout()
        self._refresh_btn = QPushButton("↻ Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        btns.addWidget(self._refresh_btn)
        self._set_btn = QPushButton("Set as Active")
        self._set_btn.setStyleSheet("background:#1565c0; color:white;")
        self._set_btn.setEnabled(False)
        self._set_btn.clicked.connect(self._set_active)
        btns.addWidget(self._set_btn)
        ll.addLayout(btns)
        left.addWidget(list_box, 1)

        outer.addLayout(left, 1)

        # ── Right: details ─────────────────────────────────────────────────
        detail_box = QGroupBox("Toolhead Details")
        dl = QVBoxLayout(detail_box)

        self._det_name = QLabel("Select a toolhead")
        self._det_name.setStyleSheet("font-size:14px; font-weight:bold; color:#ce93d8;")
        dl.addWidget(self._det_name)

        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setColumnStretch(1, 1)
        gl.setVerticalSpacing(6)
        self._det = {}
        for i, (key, label) in enumerate([
            ("footprint",  "Footprint"),
            ("offset",     "XY Offset"),
            ("tip_z",      "Tip offset Z"),
            ("z_engage",   "Engage depth"),
        ]):
            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color:#666; font-size:11px;")
            val = QLabel("—")
            val.setStyleSheet("color:#aaa; font-size:11px; font-family:monospace;")
            gl.addWidget(lbl, i, 0)
            gl.addWidget(val, i, 1)
            self._det[key] = val
        dl.addWidget(grid)
        dl.addStretch()
        outer.addWidget(detail_box, 1)

    # ── Public API ──────────────────────────────────────────────────────────

    def update_info(self, info: ToolheadInfo):
        """Receives toolhead_updated signal."""
        self._active_info = info
        if info.active:
            label = info.display_name or info.name
            self._active_lbl.setText(label)
            self._active_lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#ce93d8;")
        else:
            self._active_lbl.setText("None")
            self._active_lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#555;")
        # Refresh details if the selected item matches the now-active toolhead
        self._on_selection(self._list.currentRow())

    def update_client(self, client: SilaClient):
        self._client = client
        self._refresh()

    # ── Internals ───────────────────────────────────────────────────────────

    def _refresh(self):
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("…")
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        entries = self._client.fetch_toolhead_list()
        QTimer.singleShot(0, lambda: self._populate(entries))

    def _populate(self, entries: list[tuple[str, str]]):
        self._list.clear()
        self._names = []
        for name, display in entries:
            self._list.addItem(display)
            self._names.append(name)
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↻ Refresh")

    def _on_selection(self, row: int):
        self._set_btn.setEnabled(0 <= row < len(self._names))
        if 0 <= row < len(self._names):
            display = self._list.item(row).text()
            self._det_name.setText(display)
            info = self._active_info
            if info.active and self._names[row] == info.name:
                self._det["footprint"].setText(
                    f"{info.footprint_x:.1f} × {info.footprint_y:.1f} mm"
                )
                self._det["offset"].setText(
                    f"X={info.offset_x:.1f} mm,  Y={info.offset_y:.1f} mm"
                )
                self._det["tip_z"].setText(f"{info.tip_offset_z:.1f} mm")
                self._det["z_engage"].setText(f"{info.z_engage:.1f} mm")
            else:
                for f in self._det.values():
                    f.setText("— (set as active to view)")
        else:
            self._det_name.setText("Select a toolhead")
            for f in self._det.values():
                f.setText("—")

    def _set_active(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._names):
            self._client.set_toolhead(self._names[row])


# ── Server info panel ─────────────────────────────────────────────────────────

class ServerInfoPanel(QWidget):
    """SiLA server overview: channel status + per-feature probe results."""

    def __init__(self):
        super().__init__()
        self._feat_rows: dict[str, QLabel] = {}   # feature name → badge label
        self._feat_vbox: QVBoxLayout | None = None
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(10)
        vbox.setContentsMargins(16, 16, 16, 16)

        conn_box = QGroupBox("SiLA Server")
        cl = QVBoxLayout(conn_box)
        self._host_lbl = QLabel("Server: —")
        cl.addWidget(self._host_lbl)
        self._conn_lbl = QLabel("Status:  Disconnected")
        self._conn_lbl.setStyleSheet("color:#666;")
        cl.addWidget(self._conn_lbl)
        vbox.addWidget(conn_box)

        feat_box = QGroupBox("Discovered Features")
        self._feat_vbox = QVBoxLayout(feat_box)
        self._feat_vbox.addStretch()   # rows inserted before this
        vbox.addWidget(feat_box)
        vbox.addStretch()

    # ── Public API ──────────────────────────────────────────────────────────

    def update_host(self, host: str):
        self._host_lbl.setText(f"Server:  {host}:{SILA_PORT}")

    def update_connection(self, ok: bool):
        if ok:
            self._conn_lbl.setText("Status:  Connected")
            self._conn_lbl.setStyleSheet("color:#4caf50;")
        else:
            self._conn_lbl.setText("Status:  Not connected — retrying…")
            self._conn_lbl.setStyleSheet("color:#888;")
            for badge in self._feat_rows.values():
                badge.setText("⟳  waiting")
                badge.setStyleSheet("color:#666; font-size:11px;")

    def update_features(self, found: list[str]):
        """Called after each probe cycle with the list of reachable feature names."""
        for name in found:
            if name not in self._feat_rows:
                self._add_row(name)

        found_set = set(found)
        for name, badge in self._feat_rows.items():
            if name in found_set:
                badge.setText("✓  available")
                badge.setStyleSheet("color:#4caf50; font-size:11px;")
            else:
                badge.setText("✗  not found")
                badge.setStyleSheet("color:#f44336; font-size:11px;")

    def update_feature_stream(self, name: str, ok: bool):
        """Called when a feature's live streams start or stop."""
        if name not in self._feat_rows:
            self._add_row(name)
        badge = self._feat_rows[name]
        if ok:
            badge.setText("● streaming")
            badge.setStyleSheet("color:#4caf50; font-size:11px;")
        else:
            badge.setText("⟳  stream lost")
            badge.setStyleSheet("color:#ff9800; font-size:11px;")

    # ── Internals ───────────────────────────────────────────────────────────

    def _add_row(self, name: str):
        row = QHBoxLayout()
        row.addWidget(QLabel(name))
        row.addStretch()
        badge = QLabel("⟳  probing")
        badge.setStyleSheet("color:#666; font-size:11px;")
        row.addWidget(badge)
        # Insert before the trailing stretch
        self._feat_vbox.insertLayout(self._feat_vbox.count() - 1, row)
        self._feat_rows[name] = badge


# ── Homing panel ──────────────────────────────────────────────────────────────

class HomingPanel(QGroupBox):
    """Per-axis homing panel. Each axis can be homed independently in any order."""

    def __init__(self, client: SilaClient):
        super().__init__("Homing")
        self._client = client
        self._manual_active = False
        self._done = {k: False for k in ("x_min", "x_max", "y_min", "y_max", "z")}
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(4)

        # Status
        self._status_lbl = QLabel()
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("font-size:10px;")
        vbox.addWidget(self._status_lbl)

        # Top action row
        top = QHBoxLayout()
        self._auto_btn = QPushButton("Auto Home XY")
        self._auto_btn.setStyleSheet("background:#1565c0; color:white; font-size:11px;")
        self._auto_btn.clicked.connect(self._auto_home)
        top.addWidget(self._auto_btn)
        self._manual_btn = QPushButton("Start Manual")
        self._manual_btn.setStyleSheet("background:#e65100; color:white; font-size:11px;")
        self._manual_btn.clicked.connect(self._start_manual)
        top.addWidget(self._manual_btn)
        vbox.addLayout(top)

        # Divider
        div = QLabel()
        div.setFixedHeight(1)
        div.setStyleSheet("background:#2a2d3e; margin-top:2px;")
        vbox.addWidget(div)

        # X axis
        vbox.addWidget(self._axis_label("X axis — jog to each physical limit"))
        row_x = QHBoxLayout()
        self._x_min_btn = self._confirm_btn("X−")
        self._x_max_btn = self._confirm_btn("X+")
        self._x_min_btn.clicked.connect(self._confirm_x_min)
        self._x_max_btn.clicked.connect(self._confirm_x_max)
        row_x.addWidget(self._x_min_btn)
        row_x.addWidget(self._x_max_btn)
        vbox.addLayout(row_x)

        # Y axis
        vbox.addWidget(self._axis_label("Y axis — jog to each physical limit"))
        row_y = QHBoxLayout()
        self._y_min_btn = self._confirm_btn("Y−")
        self._y_max_btn = self._confirm_btn("Y+")
        self._y_min_btn.clicked.connect(self._confirm_y_min)
        self._y_max_btn.clicked.connect(self._confirm_y_max)
        row_y.addWidget(self._y_min_btn)
        row_y.addWidget(self._y_max_btn)
        vbox.addLayout(row_y)

        # Z axis
        vbox.addWidget(self._axis_label("Z axis — jog tip to reference surface"))
        row_z = QHBoxLayout()
        self._z_btn = QPushButton("Set Z Reference")
        self._z_btn.setStyleSheet("background:#2e7d32; color:white; font-size:11px;")
        self._z_btn.clicked.connect(self._confirm_z)
        row_z.addWidget(self._z_btn)
        row_z.addStretch()
        vbox.addLayout(row_z)

        # Reset
        reset = QPushButton("Reset All")
        reset.setStyleSheet("color:#555; font-size:10px; margin-top:2px;")
        reset.clicked.connect(self._reset)
        vbox.addWidget(reset)

        self._refresh()

    def _axis_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#555; font-size:9px; margin-top:3px;")
        return lbl

    def _confirm_btn(self, label: str) -> QPushButton:
        btn = QPushButton(f"Confirm {label}")
        btn.setStyleSheet("font-size:11px;")
        btn.setEnabled(False)
        return btn

    def _refresh(self):
        d = self._done
        x_ok = d["x_min"] and d["x_max"]
        y_ok = d["y_min"] and d["y_max"]
        z_ok = d["z"]
        active = self._manual_active

        def _style_xy(btn, done):
            if done:
                btn.setEnabled(False)
                btn.setStyleSheet("font-size:11px; background:#1b5e20; color:#666;")
            elif active:
                btn.setEnabled(True)
                btn.setStyleSheet("font-size:11px;")
            else:
                btn.setEnabled(False)
                btn.setStyleSheet("font-size:11px; color:#444;")

        _style_xy(self._x_min_btn, d["x_min"])
        _style_xy(self._x_max_btn, d["x_max"])
        _style_xy(self._y_min_btn, d["y_min"])
        _style_xy(self._y_max_btn, d["y_max"])

        # Z is always available (re-reference any time)
        if z_ok:
            self._z_btn.setText("✓ Z Referenced")
            self._z_btn.setStyleSheet("background:#1b5e20; color:#aaa; font-size:11px;")
        else:
            self._z_btn.setText("Set Z Reference")
            self._z_btn.setStyleSheet("background:#2e7d32; color:white; font-size:11px;")
        self._z_btn.setEnabled(True)

        # Status line
        missing = (["X"] if not x_ok else []) + (["Y"] if not y_ok else []) + (["Z"] if not z_ok else [])
        if not missing:
            self._status_lbl.setText("✓ All axes homed")
            self._status_lbl.setStyleSheet("font-size:10px; color:#00e676;")
        elif active:
            self._status_lbl.setText(f"Manual homing active — still needed: {', '.join(missing)}")
            self._status_lbl.setStyleSheet("font-size:10px; color:#ff9800;")
        else:
            self._status_lbl.setText(f"Not homed: {', '.join(missing)}")
            self._status_lbl.setStyleSheet("font-size:10px; color:#888;")

    def _auto_home(self):
        self._client.home_auto()
        for k in ("x_min", "x_max", "y_min", "y_max"):
            self._done[k] = True
        self._refresh()

    def _start_manual(self):
        self._client.start_manual_homing()
        self._manual_active = True
        self._refresh()

    def _confirm_x_min(self):
        self._client.confirm_x_min()
        self._done["x_min"] = True
        self._refresh()
        self._check_finish()

    def _confirm_x_max(self):
        self._client.confirm_x_max()
        self._done["x_max"] = True
        self._refresh()
        self._check_finish()

    def _confirm_y_min(self):
        self._client.confirm_y_min()
        self._done["y_min"] = True
        self._refresh()
        self._check_finish()

    def _confirm_y_max(self):
        self._client.confirm_y_max()
        self._done["y_max"] = True
        self._refresh()
        self._check_finish()

    def _confirm_z(self):
        self._client.confirm_z_reference()
        self._done["z"] = True
        self._refresh()
        self._check_finish()

    def _check_finish(self):
        if all(self._done.values()) and self._manual_active:
            self._client.finish_homing()
            self._manual_active = False
            self._refresh()

    def _reset(self):
        self._done = {k: False for k in self._done}
        self._manual_active = False
        self._refresh()

    def update_client(self, client: SilaClient):
        self._client = client


# ── Jog controls ─────────────────────────────────────────────────────────────

class JogPanel(QGroupBox):
    def __init__(self, client: SilaClient):
        super().__init__("Jog")
        self._client = client
        self._step = 5.0
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(6)

        # Step size
        row = QHBoxLayout()
        row.addWidget(QLabel("Step (mm):"))
        self._step_group = QButtonGroup(self)
        for label, val in [("0.1", 0.1), ("1", 1.0), ("5", 5.0), ("10", 10.0), ("50", 50.0)]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(40)
            btn.clicked.connect(lambda _, v=val: self._on_preset(v))
            self._step_group.addButton(btn)
            row.addWidget(btn)
            if val == 5.0:
                btn.setChecked(True)
        self._custom_step = QLineEdit()
        self._custom_step.setPlaceholderText("custom")
        self._custom_step.setFixedWidth(58)
        self._custom_step.setValidator(QDoubleValidator(0.01, 100.0, 2))
        self._custom_step.editingFinished.connect(self._apply_custom_step)
        row.addWidget(self._custom_step)
        row.addStretch()
        vbox.addLayout(row)

        # XY + Z buttons side by side
        controls = QHBoxLayout()

        xy = QGridLayout()
        xy.setSpacing(3)
        for label, dx, dy, r, c in [
            ("Y+", 0,  1, 0, 1),
            ("X-",-1,  0, 1, 0),
            ("X+", 1,  0, 1, 2),
            ("Y-", 0, -1, 2, 1),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(52, 52)
            btn.setStyleSheet("font-size:14px; font-weight:bold;")
            btn.clicked.connect(lambda _, x=dx, y=dy: self._jog_xy(x, y))
            xy.addWidget(btn, r, c)
        center = QLabel("⊕")
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setStyleSheet("color:#444; font-size:20px;")
        xy.addWidget(center, 1, 1)
        controls.addLayout(xy)

        controls.addSpacing(12)

        z_col = QVBoxLayout()
        z_col.setSpacing(3)
        z_up = QPushButton("Z+")
        z_dn = QPushButton("Z-")
        for btn in (z_up, z_dn):
            btn.setFixedSize(52, 52)
            btn.setStyleSheet("font-size:14px; font-weight:bold; background:#2d1f50;")
        z_up.clicked.connect(lambda: self._jog_z(1))
        z_dn.clicked.connect(lambda: self._jog_z(-1))
        z_lbl = QLabel("Z")
        z_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        z_lbl.setStyleSheet("color:#666;")
        z_col.addWidget(z_up)
        z_col.addWidget(z_lbl)
        z_col.addWidget(z_dn)
        controls.addLayout(z_col)
        controls.addStretch()
        vbox.addLayout(controls)

        hint = QLabel("Click grid to move  |  Arrow keys = XY  |  PgUp / PgDn = Z")
        hint.setStyleSheet("color:#444; font-size:9px;")
        vbox.addWidget(hint)

    def _on_preset(self, val: float):
        self._step = val
        self._custom_step.clear()

    def _apply_custom_step(self):
        text = self._custom_step.text().strip()
        if not text:
            return
        try:
            val = float(text)
        except ValueError:
            self._custom_step.clear()
            return
        val = max(0.01, min(100.0, val))
        self._custom_step.setText(f"{val:g}")
        self._step = val
        for btn in self._step_group.buttons():
            btn.setChecked(False)

    def _jog_xy(self, dx, dy):
        self._client.jog(dx=dx * self._step, dy=dy * self._step)

    def _jog_z(self, dz):
        self._client.jog(dz=dz * self._step)

    def handle_key(self, key):
        mapping = {
            Qt.Key.Key_Left:     (-1, 0, 0),
            Qt.Key.Key_Right:    ( 1, 0, 0),
            Qt.Key.Key_Up:       ( 0, 1, 0),
            Qt.Key.Key_Down:     ( 0,-1, 0),
            Qt.Key.Key_PageUp:   ( 0, 0, 1),
            Qt.Key.Key_PageDown: ( 0, 0,-1),
        }
        if key in mapping:
            dx, dy, dz = mapping[key]
            self._client.jog(
                dx=dx * self._step,
                dy=dy * self._step,
                dz=dz * self._step,
            )

    def update_client(self, c: SilaClient):
        self._client = c


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    Top-level window.

    Connection bar (always visible at top — SiLA server dot)
    ──────────────────────────────────────────────────────────
    QTabWidget  (starts with only "Server" tab; feature tabs injected dynamically
                 after _discover_and_stream() probes the server)
      ├─ "Motion Platform"  added when feature found, has its own ● dot
      ├─ "Toolheads"        added alongside Motion Platform
      └─ "Server"           always present; shows SiLA + per-feature status
    ──────────────────────────────────────────────────────────
    Error toast
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chem Bench Control")
        self.setMinimumSize(960, 600)
        self._client = SilaClient()
        self._homed = False
        self._current_z = 0.0

        # Feature tab widgets are built once then inserted/removed from tab widget
        self._motion_widget: QWidget | None = None
        self._toolhead_mgr: ToolheadManagerPanel | None = None
        self._motion_dot: QLabel | None = None   # per-feature indicator in motion tab
        self._shown_features: set[str] = set()   # track which tabs are currently added

        self._build_ui()

        # Always-on signals
        self._client.connection_changed.connect(self._on_connected)
        self._client.error_occurred.connect(self._show_error)
        self._client.features_discovered.connect(self._on_features_discovered)
        self._client.feature_state_changed.connect(self._on_feature_state)
        # Motion-specific signals connected lazily inside _on_features_discovered

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: self._toast.setVisible(False))

        self._server_panel.update_host("localhost")
        self._client.connect_to("localhost")

        QApplication.instance().installEventFilter(self)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # SiLA server connection bar (top, always visible)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("SiLA server:"))
        self._host_input = QLineEdit("localhost")
        self._host_input.setMaximumWidth(200)
        self._host_input.returnPressed.connect(self._reconnect)
        bar.addWidget(self._host_input)
        conn_btn = QPushButton("Connect")
        conn_btn.setMaximumWidth(80)
        conn_btn.clicked.connect(self._reconnect)
        bar.addWidget(conn_btn)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#f44336; font-size:16px;")
        bar.addWidget(self._dot)
        self._status_lbl = QLabel("Connecting…")
        self._status_lbl.setStyleSheet("color:#666;")
        bar.addWidget(self._status_lbl)
        bar.addStretch()
        root.addLayout(bar)

        # Tab widget — only Server tab to start
        self._tabs = QTabWidget()
        self._server_panel = ServerInfoPanel()
        self._tabs.addTab(self._server_panel, "Server")
        root.addWidget(self._tabs, 1)

        # Error toast
        self._toast = QLabel()
        self._toast.setWordWrap(True)
        self._toast.setVisible(False)
        self._toast.setStyleSheet(
            "background:#7f1d1d; color:#fca5a5;"
            "border:1px solid #ef4444; border-radius:4px;"
            "padding:6px 10px; font-size:11px;"
        )
        root.addWidget(self._toast)

        self.setStyleSheet("""
            QMainWindow, QWidget { background:#111318; color:#dde1ec; }
            QTabWidget::pane { border:1px solid #2a2d3e; }
            QTabBar::tab {
                background:#161924; color:#888; padding:6px 16px;
                border:1px solid #2a2d3e; border-bottom:none;
                border-top-left-radius:4px; border-top-right-radius:4px;
            }
            QTabBar::tab:selected { background:#1e2130; color:#dde1ec; }
            QTabBar::tab:hover    { background:#1a1f2e; }
            QGroupBox {
                border:1px solid #2a2d3e; border-radius:4px;
                margin-top:8px; padding-top:4px; font-weight:bold;
            }
            QGroupBox::title { subcontrol-origin:margin; left:8px; color:#888; }
            QPushButton {
                background:#1e2130; color:#dde1ec; border:1px solid #333;
                border-radius:4px; padding:4px 8px;
            }
            QPushButton:hover   { background:#272b3e; }
            QPushButton:pressed { background:#111318; }
            QPushButton:checked { background:#1565c0; border-color:#1976d2; }
            QLineEdit {
                background:#161924; border:1px solid #333; border-radius:4px;
                padding:4px; color:#dde1ec;
            }
            QListWidget {
                background:#161924; border:1px solid #2a2d3e;
                alternate-background-color:#1a1f2e;
            }
            QListWidget::item:selected { background:#1565c0; color:white; }
        """)

    def _build_motion_tab(self) -> QWidget:
        """Build the Motion Platform tab content (called once on first discovery)."""
        wrapper = QWidget()
        vbox = QVBoxLayout(wrapper)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Per-feature connection status bar at the very top of the tab
        status_bar = QWidget()
        status_bar.setFixedHeight(28)
        status_bar.setStyleSheet("background:#0d1117; border-bottom:1px solid #2a2d3e;")
        sb = QHBoxLayout(status_bar)
        sb.setContentsMargins(10, 0, 10, 0)
        self._motion_dot = QLabel("●")
        self._motion_dot.setStyleSheet("color:#ff9800; font-size:13px;")
        sb.addWidget(self._motion_dot)
        self._motion_feat_lbl = QLabel("Motion Platform  —  waiting for hardware…")
        self._motion_feat_lbl.setStyleSheet("color:#888; font-size:11px;")
        sb.addWidget(self._motion_feat_lbl)
        sb.addStretch()
        vbox.addWidget(status_bar)

        # Main content
        content_widget = QWidget()
        content = QHBoxLayout(content_widget)
        content.setSpacing(8)
        content.setContentsMargins(4, 4, 4, 4)

        # Left column
        left = QVBoxLayout()
        left.setSpacing(6)

        pos_box = QGroupBox("Status")
        pl = QVBoxLayout(pos_box)
        pl.setSpacing(4)
        self._state_lbl = QLabel("State: ---")
        self._state_lbl.setStyleSheet("font-family:monospace; font-size:13px;")
        pl.addWidget(self._state_lbl)

        self._more_btn = QPushButton("Show position ▾")
        self._more_btn.setFlat(True)
        self._more_btn.setStyleSheet(
            "color:#555; font-size:10px; text-align:left; border:none; padding:0;"
        )
        self._more_btn.clicked.connect(self._toggle_position)
        pl.addWidget(self._more_btn)

        self._pos_detail = QWidget()
        dl = QVBoxLayout(self._pos_detail)
        dl.setContentsMargins(0, 2, 0, 0)
        dl.setSpacing(1)
        self._x_lbl = QLabel("X:  ---")
        self._y_lbl = QLabel("Y:  ---")
        self._z_lbl = QLabel("Z:  ---")
        for lbl in (self._x_lbl, self._y_lbl, self._z_lbl):
            lbl.setStyleSheet("font-family:monospace; font-size:12px; color:#888;")
            dl.addWidget(lbl)
        self._pos_detail.setVisible(False)
        pl.addWidget(self._pos_detail)
        left.addWidget(pos_box)

        self._toolhead_panel = ToolheadPanel(self._client)
        left.addWidget(self._toolhead_panel)
        self._homing = HomingPanel(self._client)
        left.addWidget(self._homing)
        left.addStretch()
        content.addLayout(left)

        # Right column
        right = QVBoxLayout()
        grid_row = QHBoxLayout()
        grid_row.setSpacing(4)
        self._grid = PositionGrid()
        grid_row.addWidget(self._grid, 1)
        self._zbar = ZBar()
        grid_row.addWidget(self._zbar)
        right.addLayout(grid_row, 1)
        self._jog = JogPanel(self._client)
        right.addWidget(self._jog)
        content.addLayout(right, 1)

        vbox.addWidget(content_widget, 1)
        return wrapper

    # ── Dynamic feature tab management ────────────────────────────────────

    def _on_features_discovered(self, features: list[str]):
        """Insert tabs for newly found features; update server panel."""
        new = set(features) - self._shown_features

        if "Motion Platform" in new:
            if self._motion_widget is None:
                # First time: build widgets and wire up motion signals
                self._motion_widget = self._build_motion_tab()
                self._toolhead_mgr = ToolheadManagerPanel(self._client)
                self._grid.move_requested.connect(self._on_grid_click)
                self._client.position_updated.connect(self._on_position)
                self._client.state_updated.connect(self._on_state)
                self._client.toolhead_updated.connect(self._on_toolhead)
            else:
                # Reconnect to same/different server: refresh panels
                self._toolhead_panel.update_client(self._client)
                self._toolhead_mgr.update_client(self._client)
                self._homing.update_client(self._client)
                self._jog.update_client(self._client)

            # Insert before Server tab
            server_idx = self._tabs.indexOf(self._server_panel)
            self._tabs.insertTab(server_idx, self._toolhead_mgr, "Toolheads")
            self._tabs.insertTab(server_idx, self._motion_widget, "Motion Platform")
            self._tabs.setCurrentIndex(0)
            self._shown_features.add("Motion Platform")

        # Remove tabs for features no longer present
        gone = self._shown_features - set(features)
        if "Motion Platform" in gone and self._motion_widget is not None:
            self._tabs.removeTab(self._tabs.indexOf(self._toolhead_mgr))
            self._tabs.removeTab(self._tabs.indexOf(self._motion_widget))
            self._shown_features.discard("Motion Platform")

        self._server_panel.update_features(features)

    def _on_feature_state(self, feature: str, ok: bool):
        """Update the per-feature ● indicator inside the feature's tab."""
        if feature == "Motion Platform" and self._motion_dot is not None:
            self._motion_dot.setStyleSheet(
                f"color:{'#4caf50' if ok else '#ff9800'}; font-size:13px;"
            )
            self._motion_feat_lbl.setText(
                "Motion Platform  —  hardware connected" if ok
                else "Motion Platform  —  waiting for hardware…"
            )
        self._server_panel.update_feature_stream(feature, ok)

    # ── General slots ──────────────────────────────────────────────────────

    def _reconnect(self):
        host = self._host_input.text().strip()
        if not host:
            return
        self._server_panel.update_host(host)
        # Remove feature tabs so they're re-added cleanly after re-discovery
        if self._motion_widget and self._tabs.indexOf(self._motion_widget) >= 0:
            self._tabs.removeTab(self._tabs.indexOf(self._toolhead_mgr))
            self._tabs.removeTab(self._tabs.indexOf(self._motion_widget))
        self._shown_features.clear()
        self._client.connect_to(host)

    def _show_error(self, msg: str):
        self._toast.setText(f"⚠  {msg}")
        self._toast.setVisible(True)
        self._toast_timer.start(6000)

    def _toggle_position(self):
        visible = not self._pos_detail.isVisible()
        self._pos_detail.setVisible(visible)
        self._more_btn.setText("Hide position ▴" if visible else "Show position ▾")

    def _on_position(self, x, y, z):
        self._x_lbl.setText(f"X:  {x:8.2f} mm")
        self._y_lbl.setText(f"Y:  {y:8.2f} mm")
        self._z_lbl.setText(f"Z:  {z:8.2f} mm")
        self._current_z = z
        self._grid.set_position(x, y, self._homed)
        self._zbar.set_z(z, self._homed)

    def _on_toolhead(self, info: ToolheadInfo):
        self._toolhead_panel.update_info(info)
        self._toolhead_mgr.update_info(info)
        self._grid.set_toolhead(info if info.active else None)
        self._zbar.set_toolhead(info if info.active else None)

    def _on_grid_click(self, x: float, y: float):
        self._client.move_to(x, y, self._current_z)

    def _on_state(self, state: str):
        self._state_lbl.setText(state)
        self._homed = state.lower() == "ready"

    def _on_connected(self, ok: bool):
        color = "#4caf50" if ok else "#f44336"
        self._dot.setStyleSheet(f"color:{color}; font-size:16px;")
        self._status_lbl.setText(
            f"Connected — {self._client._host}" if ok
            else "Not connected — retrying…"
        )
        self._server_panel.update_connection(ok)

    # ── Key event filter ───────────────────────────────────────────────────

    _JOG_KEYS = {
        Qt.Key.Key_Left, Qt.Key.Key_Right,
        Qt.Key.Key_Up, Qt.Key.Key_Down,
        Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
    }

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in self._JOG_KEYS
            and not self._host_input.hasFocus()
            and self._motion_widget is not None
        ):
            self._jog.handle_key(event.key())
            return True
        return super().eventFilter(obj, event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Chem Bench Control")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
