r"""Low-level UART/serial driver for the Atlas Scientific EZO-pH circuit.

Shares the EZO command protocol with the I2C driver via
:class:`~rxn_bench_ph.ezo_commands.EZOCommandSet`; this class supplies the
serial transport. Where the I2C protocol prefixes a status byte, the UART
protocol is line-oriented ASCII:

    - commands are written terminated with a carriage return: ``R\r``
    - each reply is a carriage-return-terminated line
    - response codes ``*OK`` (command accepted) and ``*ER`` (unknown command /
      error) frame each exchange; other ``*``-prefixed lines (``*RS`` reset,
      ``*WA`` wake, ...) are asynchronous status and are ignored
    - by default the EZO streams a reading every second ("continuous mode");
      that is disabled at startup (``C,0``) so reads are clean request/response

The driver talks to a minimal port object exposing ``write(bytes)`` and
``read_until(expected) -> bytes`` (pyserial's ``serial.Serial`` satisfies this,
as does :class:`~rxn_bench_ph.mock_uart.MockEZOUart` for tests). This mirrors
how the I2C driver depends only on a small ``write``/``read`` bus interface.
"""
from __future__ import annotations

import logging
import time

from rxn_bench_ph.ezo_commands import EZOCommandSet

log = logging.getLogger(__name__)

# EZO circuits default to 9600 baud, 8N1 in UART mode.
DEFAULT_BAUD_RATE = 9600

_CR = b"\r"
_OK = b"*OK"
_ERR = b"*ER"


class AtlasScientificEZOUart(EZOCommandSet):
    """Low-level EZO-pH command driver over UART. Speaks the Atlas Scientific serial protocol."""

    def __init__(self, port, disable_continuous: bool = True) -> None:
        """
        Args:
            port: An open serial port exposing ``write(data: bytes) -> None`` and
                ``read_until(expected: bytes) -> bytes`` (e.g. ``serial.Serial``).
            disable_continuous: Send ``C,0`` at startup to stop the EZO's default
                once-per-second streaming so reads are clean request/response.
                Leave True for real hardware.
        """
        self._port = port
        if disable_continuous:
            self._disable_continuous_mode()

    def _disable_continuous_mode(self) -> None:
        """Turn off continuous readings and drain anything already queued."""
        try:
            self._send_command("C,0")
            self._read_response(delay_ms=300)
        except (IOError, ValueError) as exc:
            # Non-fatal: some firmware/wiring may not ack promptly. Reads still
            # work; they just have to tolerate an occasional stray reading.
            log.warning("Could not disable EZO continuous mode: %s", exc)
        reset = getattr(self._port, "reset_input_buffer", None)
        if callable(reset):
            reset()

    def _send_command(self, cmd: str) -> None:
        """Write an ASCII command terminated with a carriage return.

        Drains any pending input first so a stale line - the unread ``*OK`` from
        a send-only command like ``Find``/``Sleep``, or a stray continuous
        reading - can't be mistaken for this command's reply.
        """
        reset = getattr(self._port, "reset_input_buffer", None)
        if callable(reset):
            reset()
        self._port.write(cmd.encode("ascii") + _CR)

    def _read_response(self, delay_ms: int = 900) -> str:
        """Read CR-terminated lines until the command is framed by ``*OK``/``*ER``.

        Returns the data line for a data command, or an empty string for an
        ack-only command. ``delay_ms`` (the I2C processing delay) sizes the
        read timeout so slow commands like calibration still complete.

        Raises:
            IOError:    No response arrived before the timeout.
            ValueError: The sensor replied ``*ER`` (unknown command / syntax error).
        """
        deadline = time.monotonic() + max(delay_ms / 1000.0, 0.5) + 0.5
        data: bytes | None = None
        while time.monotonic() < deadline:
            line = self._port.read_until(_CR)
            if not line.endswith(_CR):
                continue  # read timed out with no complete line; re-check deadline
            text = line.rstrip(_CR).strip()
            if not text:
                continue
            if text == _OK:
                return data.decode("ascii").strip() if data is not None else ""
            if text == _ERR:
                raise ValueError("Sensor reported an error (*ER) for the last command")
            if text.startswith(b"*"):
                continue  # asynchronous status (*RS, *WA, *RE, *SL, ...) - ignore
            data = text  # a data line; keep reading for the trailing *OK
        if data is not None:
            return data.decode("ascii").strip()
        raise IOError("Timeout waiting for UART response from sensor")
