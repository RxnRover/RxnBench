"""pH sensor connection - human-maintained layer on top of the generated base.

Stream registration and _rpc boilerplate live in PHConnectionBase (generated from
connections/specs/ph_sensor.yaml). The protobuf helpers here are hand-rolled
because no compiled stubs exist for the pH feature yet. Generate stubs with
gen_proto.py on the backend to replace these helpers and the _handle_ph_raw
implementation with a standard decode_type entry in the spec.
"""
from __future__ import annotations

import struct
import threading

from PySide6.QtCore import Signal

from .generated_connection import PHConnectionBase


# ---------------------------------------------------------------------------
# Hand-rolled protobuf helpers
# ---------------------------------------------------------------------------

def _varint(data: bytes, i: int) -> tuple[int, int]:
    n, shift = 0, 0
    while True:
        b = data[i]; i += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, i
        shift += 7


def _get_field(data: bytes, field_num: int) -> bytes | None:
    """Return raw bytes of the first LEN field numbered field_num."""
    i = 0
    while i < len(data):
        tag, i = _varint(data, i)
        fn, wt = tag >> 3, tag & 0x7
        if wt == 2:
            length, i = _varint(data, i)
            if fn == field_num:
                return data[i: i + length]
            i += length
        elif wt == 0: _, i = _varint(data, i)
        elif wt == 1: i += 8
        elif wt == 5: i += 4
    return None


def _make_field(field_num: int, msg_bytes: bytes) -> bytes:
    def _enc(n: int) -> bytes:
        out = []
        while n > 0x7F:
            out.append((n & 0x7F) | 0x80); n >>= 7
        out.append(n); return bytes(out)
    return _enc((field_num << 3) | 2) + _enc(len(msg_bytes)) + msg_bytes


class _Real:
    """SiLA Real (double) - wire: field 1 fixed64."""
    @staticmethod
    def encode(value: float) -> bytes:
        return b"\x09" + struct.pack("<d", float(value))

    @staticmethod
    def decode(data: bytes) -> float:
        if data and data[0] == 0x09 and len(data) >= 9:
            return struct.unpack("<d", data[1:9])[0]
        return float("nan")


class _String:
    """SiLA String - wire: field 1 LEN (UTF-8)."""
    @staticmethod
    def encode(value: str) -> bytes:
        b = value.encode("utf-8")
        n = len(b)
        out = []
        while n > 0x7F:
            out.append((n & 0x7F) | 0x80); n >>= 7
        out.append(n)
        return b"\x0a" + bytes(out) + b

    @staticmethod
    def decode(data: bytes) -> str:
        if len(data) >= 2 and data[0] == 0x0a:
            length, i = 0, 1
            shift = 0
            while True:
                byte = data[i]; i += 1
                length |= (byte & 0x7F) << shift
                if not (byte & 0x80):
                    break
                shift += 7
            return data[i: i + length].decode("utf-8", errors="replace")
        return ""


# ---------------------------------------------------------------------------
# PHConnection
# ---------------------------------------------------------------------------

class PHConnection(PHConnectionBase):
    """Human-owned pH sensor client.

    Add convenience methods and higher-level workflows here.
    Stream boilerplate is in PHConnectionBase (generated).
    """

    slope_ready = Signal(str)

    # --- Custom stream handler ---

    def _handle_ph_raw(self, raw: bytes) -> None:
        inner = _get_field(raw, 1)
        if inner is not None:
            self.ph_updated.emit(_Real.decode(inner))

    # --- Commands ---

    def fetch_slope(self) -> None:
        """Request the probe slope from the server (non-blocking)."""
        threading.Thread(target=self._do_fetch_slope, daemon=True).start()

    def _do_fetch_slope(self) -> None:
        try:
            raw   = self._channel.unary_unary(self._rpc("Get_ProbeSlope"))(b"", timeout=5.0)
            inner = _get_field(bytes(raw), 1)
            self.slope_ready.emit(_String.decode(inner) if inner else "")
        except Exception as e:
            self.error_occurred.emit(f"Get_ProbeSlope: {e}")

    def calibrate(self, point: str, value: float) -> None:
        """Send a calibration command to the probe (non-blocking).

        Args:
            point: Calibration point - one of ``'mid'``, ``'low'``, ``'high'``, or ``'clear'``.
            value: Known pH value of the calibration buffer.
        """
        params = (
            _make_field(1, _String.encode(point)) +
            _make_field(2, _Real.encode(value))
        )
        threading.Thread(target=self._do_calibrate, args=(params,), daemon=True).start()

    def _do_calibrate(self, params: bytes) -> None:
        try:
            self._channel.unary_unary(self._rpc("Calibrate"))(params, timeout=30.0)
            self._do_fetch_slope()
        except Exception as e:
            self.error_occurred.emit(f"Calibrate: {e}")
