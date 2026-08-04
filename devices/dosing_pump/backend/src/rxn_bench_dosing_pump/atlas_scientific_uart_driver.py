r"""Low-level UART/serial driver for the Atlas Scientific EZO-PMP circuit.

Supplies the serial transport for
:class:`~rxn_bench_dosing_pump.ezo_pmp_commands.EZOPumpCommandSet`. The UART
protocol is line-oriented ASCII:

    - commands are written terminated with a carriage return: ``D,15\r``
    - each reply is a carriage-return-terminated line
    - response codes ``*OK`` (accepted) and ``*ER`` (unknown command / error)
      frame each exchange
    - ``*DONE,<volume>`` is *also* a terminator: it is the only reply to ``X``
      (stop), and it additionally arrives unsolicited whenever a dispense
      finishes on its own
    - ``*MINVOL`` (volume below 0.5ml) and ``*TOOFAST`` (rate above the
      calibrated maximum) are command rejections and raise
    - other ``*``-prefixed lines (``*RS`` reset, ``*WA`` wake, ``*OV``/``*UV``
      supply out of range, ...) are asynchronous status and are ignored
    - by default the pump streams the dispensed volume every second
      ("continuous mode"); that is disabled at startup (``C,0``) so reads are
      clean request/response

The driver talks to a minimal port object exposing ``write(bytes)`` and
``read_until(expected) -> bytes`` - pyserial's ``serial.Serial`` satisfies
this, as does :class:`~rxn_bench_dosing_pump.mock_uart.MockEZOPumpUart`.
"""
from __future__ import annotations

import logging
import time

from rxn_bench_dosing_pump.ezo_pmp_commands import DELAY_MS, EZOPumpCommandSet

log = logging.getLogger(__name__)

# EZO circuits default to 9600 baud, 8N1 in UART mode.
DEFAULT_BAUD_RATE = 9600

_CR = b"\r"
_OK = b"*OK"
_ERR = b"*ER"
_DONE = b"*DONE"

# Command rejections the pump reports in place of *ER, mapped to their cause.
_REJECTIONS = {
    b"*MINVOL": "requested volume is below the pump's 0.5ml minimum",
    b"*TOOFAST": "requested flow rate exceeds the pump's calibrated maximum",
}


class AtlasScientificEZOPumpUart(EZOPumpCommandSet):
    """Low-level EZO-PMP command driver over UART. Speaks the Atlas Scientific serial protocol."""

    def __init__(self, port, disable_continuous: bool = True) -> None:
        """
        Args:
            port: An open serial port exposing ``write(data: bytes) -> None`` and
                ``read_until(expected: bytes) -> bytes`` (e.g. ``serial.Serial``).
            disable_continuous: Send ``C,0`` at startup to stop the pump's default
                once-per-second streaming so reads are clean request/response.
                Leave True for real hardware.
        """
        super().__init__()
        self._port = port
        # Volume reported by the most recent *DONE, including unsolicited ones
        # seen while reading some other command's reply.
        self.last_completed_volume: float | None = None
        if disable_continuous:
            self._disable_continuous_mode()

    def _disable_continuous_mode(self) -> None:
        """Turn off continuous volume reporting and drain anything already queued."""
        try:
            self._send_command("C,0")
            self._read_response()
        except (IOError, ValueError) as exc:
            # Non-fatal: some firmware/wiring may not ack promptly. Reads still
            # work; they just have to tolerate an occasional stray reading.
            log.warning("Could not disable EZO-PMP continuous mode: %s", exc)
        reset = getattr(self._port, "reset_input_buffer", None)
        if callable(reset):
            reset()

    def _send_command(self, cmd: str) -> None:
        """Write an ASCII command terminated with a carriage return.

        Drains any pending input first so a stale line - an unsolicited
        ``*DONE`` from a dispense that just finished, or a stray continuous
        reading - can't be mistaken for this command's reply.
        """
        reset = getattr(self._port, "reset_input_buffer", None)
        if callable(reset):
            reset()
        self._port.write(cmd.encode("ascii") + _CR)

    def _read_response(self, delay_ms: int = DELAY_MS, done_terminates: bool = False) -> str:
        """Read CR-terminated lines until the command is framed by a terminator.

        Returns the data line for a data command, or an empty string for an
        ack-only command. ``delay_ms`` (the I2C processing delay) sizes the read
        timeout.

        ``*DONE`` is only treated as this command's reply when *done_terminates*
        says to expect one (the ``X`` case). Otherwise it is recorded in
        :attr:`last_completed_volume` and skipped like any other asynchronous
        status - a dispense finishing mid-query must not be mistaken for the
        reply, whichever side of the real data line it lands on.

        Args:
            delay_ms: The command's processing delay, sizing the read timeout.
            done_terminates: True only for ``X``, whose reply is a ``*DONE`` line.

        Raises:
            IOError:    No response arrived before the timeout.
            ValueError: The pump replied ``*ER``, ``*MINVOL``, or ``*TOOFAST``.
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
                raise ValueError("Pump reported an error (*ER) for the last command")
            upper = text.upper()
            rejection = next((r for c, r in _REJECTIONS.items() if upper.startswith(c)), None)
            if rejection is not None:
                raise ValueError(f"Pump rejected the command: {rejection}")
            # Firmware spells this '*DONE' on some datasheet pages, '*Done' on others.
            if upper.startswith(_DONE):
                self._record_done(text)
                if done_terminates:
                    return text.decode("ascii").strip()
                continue
            if text.startswith(b"*"):
                continue  # asynchronous status (*RS, *WA, *RE, *OV, *UV, ...) - ignore
            data = text  # a data line; keep reading for the trailing *OK
        if data is not None:
            return data.decode("ascii").strip()
        raise IOError("Timeout waiting for UART response from pump")

    def _record_done(self, line: bytes) -> None:
        """Remember the volume from a ``*DONE,<volume>`` line, ignoring malformed ones."""
        parts = line.decode("ascii", errors="replace").split(",")
        if len(parts) > 1:
            try:
                self.last_completed_volume = float(parts[1])
            except ValueError:
                log.debug("Unparseable *DONE volume in %r", line)
