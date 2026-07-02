"""
MyDevice connection - human-maintained layer on top of the generated base.

Stream registration and _rpc boilerplate live in MyDeviceConnectionBase
(generated from connection_spec.yaml). No compiled protobuf stubs exist for
this template, so the hand-rolled wire-format helpers below decode the raw
bytes - see devices/ph_sensor/frontend/connection.py for the same pattern
applied to a real feature.

TODO: rename MyDeviceConnection and _handle_measurement_raw / perform_action
      to match your device. Generate proto stubs on the backend to drop the
      hand-rolled helpers and switch to the gantry-style decode_type pattern.
"""
from __future__ import annotations

import threading

from .generated_connection import MyDeviceConnectionBase


# ---------------------------------------------------------------------------
# Hand-rolled protobuf helpers (minimal subset - see ph_sensor for the full set)
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


class _Real:
    """SiLA Real (double) - wire: field 1 fixed64."""
    import struct as _struct

    @classmethod
    def encode(cls, value: float) -> bytes:
        return b"\x09" + cls._struct.pack("<d", float(value))

    @classmethod
    def decode(cls, data: bytes) -> float:
        if data and data[0] == 0x09 and len(data) >= 9:
            return cls._struct.unpack("<d", data[1:9])[0]
        return float("nan")


def _make_field(field_num: int, msg_bytes: bytes) -> bytes:
    def _enc(n: int) -> bytes:
        out = []
        while n > 0x7F:
            out.append((n & 0x7F) | 0x80); n >>= 7
        out.append(n); return bytes(out)
    return _enc((field_num << 3) | 2) + _enc(len(msg_bytes)) + msg_bytes


# ---------------------------------------------------------------------------
# MyDeviceConnection
# ---------------------------------------------------------------------------

class MyDeviceConnection(MyDeviceConnectionBase):
    """Human-owned MyDevice client.

    Add convenience methods and higher-level workflows here.
    Stream boilerplate is in MyDeviceConnectionBase (generated).
    """

    # --- Custom stream handler ---

    def _handle_measurement_raw(self, raw: bytes) -> None:
        inner = _get_field(raw, 1)
        if inner is not None:
            self.measurement_updated.emit(_Real.decode(inner))

    # --- Commands ---

    def perform_action(self, parameter: float) -> None:
        """Send the perform_action command to the device (non-blocking).

        TODO: rename and update the docstring to describe your actual command.
        """
        params = _make_field(1, _Real.encode(parameter))
        threading.Thread(target=self._do_perform_action, args=(params,), daemon=True).start()

    def _do_perform_action(self, params: bytes) -> None:
        try:
            self._channel.unary_unary(self._rpc("PerformAction"))(params, timeout=5.0)
        except Exception as e:
            self.error_occurred.emit(f"PerformAction: {e}")
