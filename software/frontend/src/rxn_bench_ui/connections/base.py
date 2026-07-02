"""
Base class for all SiLA device connections in the frontend.

Each device has two connection files in its devices/<name>/ folder:
  generated_connection.py - generated from connections/specs/<name>.yaml, do not edit
  connection.py           - human-maintained; extends the generated base

Run scripts/gen_connections.py to regenerate a device's generated_connection.py.
"""
from __future__ import annotations

import base64
import re
import threading
from typing import Any, Callable

import grpc
from PySide6.QtCore import QObject, Signal

SILA_PORT = 50051


def _format_error(method: str, exc: Exception) -> str:
    """Extract a human-readable message from a gRPC exception, trying to decode base64 details."""
    raw = str(exc)
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


class _FeatureConnection(QObject):
    """Base for typed SiLA feature connections.

    Manages one gRPC channel with reconnect support. Subclasses override
    _on_connected() to start feature-specific streams and issue initial requests.
    All stream threads exit automatically when a new connection supersedes them
    via the generation counter (_gen).
    """

    connection_changed    = Signal(bool)       # True = channel READY
    error_occurred        = Signal(str)
    feature_state_changed = Signal(str, bool)  # (feature_name, streams_ok)

    def __init__(self) -> None:
        super().__init__()
        self._channel: grpc.Channel | None = None
        self._stop    = threading.Event()
        self._host    = ""
        self._gen:    int = 0

    @property
    def host(self) -> str:
        return self._host

    def connect_to(self, host: str, port: int = SILA_PORT) -> None:
        """Open a gRPC channel to host:port and start feature streams.

        Args:
            host: IP address or hostname of the SiLA server.
            port: gRPC port number.
        """
        self._stop.set()
        if self._channel:
            self._channel.close()

        self._host = host
        self._gen += 1
        self._stop    = threading.Event()
        self._channel = grpc.insecure_channel(f"{host}:{port}")

        _stop_ref = self._stop
        def _on_channel_state(connectivity: grpc.ChannelConnectivity) -> None:
            if not _stop_ref.is_set():
                self.connection_changed.emit(
                    connectivity == grpc.ChannelConnectivity.READY
                )
        self._channel.subscribe(_on_channel_state, try_to_connect=True)

        # args tuple evaluated immediately - captures current _gen value.
        threading.Thread(target=self._on_connected, args=(self._gen,), daemon=True).start()

    def disconnect(self) -> None:
        """Cancel all streams and close the channel."""
        self._stop.set()

    def _on_connected(self, gen: int) -> None:
        """Called in a daemon thread after each connect_to(). Override in subclass."""

    def _spawn_stream(
        self,
        gen: int,
        rpc_path: str,
        handler: Callable[[Any], None],
        *,
        decode: Callable[[bytes], Any] = bytes,
        feature_name: str = "",
        retry_delay: float = 3.0,
    ) -> None:
        """Spawn a daemon thread that streams rpc_path, calling handler(decode(raw))."""
        threading.Thread(
            target=self._stream_loop,
            args=(gen, rpc_path, handler),
            kwargs={"decode": decode, "feature_name": feature_name, "retry_delay": retry_delay},
            daemon=True,
        ).start()

    def _stream_loop(
        self,
        gen: int,
        rpc_path: str,
        handler: Callable[[Any], None],
        *,
        decode: Callable[[bytes], Any] = bytes,
        feature_name: str = "",
        retry_delay: float = 3.0,
    ) -> None:
        while self._gen == gen and not self._stop.is_set():
            first = True
            try:
                for raw in self._channel.unary_stream(rpc_path)(b""):
                    if self._gen != gen or self._stop.is_set():
                        return
                    if first:
                        if feature_name:
                            self.feature_state_changed.emit(feature_name, True)
                        first = False
                    handler(decode(bytes(raw)))
            except Exception:
                if feature_name:
                    self.feature_state_changed.emit(feature_name, False)
                if self._gen != gen or self._stop.wait(retry_delay):
                    return

    def _call(self, rpc_path: str, request: bytes = b"") -> None:
        """Send a unary gRPC request, emitting error_occurred on failure."""
        try:
            self._channel.unary_unary(rpc_path)(request)
        except Exception as e:
            method = rpc_path.rsplit("/", 1)[-1]
            print(f"[gRPC] {method} error: {e}")
            self.error_occurred.emit(_format_error(method, e))

    def _fire(self, rpc_path: str, request: bytes = b"") -> None:
        """Issue a command without blocking the caller."""
        threading.Thread(target=self._call, args=(rpc_path, request), daemon=True).start()
