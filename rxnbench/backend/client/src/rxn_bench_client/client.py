"""
Blocking Python client for Rxn Bench SiLA servers.

Intended for use in experiment scripts run on the backend machine.

Usage::

    from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

    with RxnBenchClient() as bench:
        bench.connect("gantry", Gantry,  server="rxn-bench-gantry")
        bench.connect("ph",     PHProbe, server="rxn-bench-ph")

        bench.set_log_output("results.csv")
        bench.gantry.mount_toolhead("ph_probe")

        for well in bench.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well, stabilize=3):
                bench.log(ph=bench.ph.read())

        bench.gantry.save_and_park()

No gantry? No problem - just connect what you have::

    with RxnBenchClient() as bench:
        bench.connect("ph",          PHProbe,       server="rxn-bench-ph")
        bench.connect("spectrometer", Spectrometer, server="rxn-bench-spec")

        bench.log(ph=bench.ph.read(), abs600=bench.spectrometer.read(600))
"""

from __future__ import annotations

import contextlib
import csv
import datetime
import os
import pathlib
import socket
import time
from typing import Any, Generator, Type

from sila2.client import SilaClient


class ExperimentStopped(Exception):
    """Raised by check_pause_stop() when the UI stop button has been pressed."""


def _once(prop) -> object:
    """Subscribe to a SiLA observable property, take one value, and cancel."""
    sub = prop.subscribe()
    try:
        return next(sub)
    finally:
        sub.cancel()


def _discover_sila_server(server_name: str, timeout: float = 5.0) -> tuple[str, int]:
    """Find a SiLA server on the local network by name using mDNS.

    SiLA servers broadcast themselves via Zeroconf as ``_sila._tcp.local.``
    services. Matches *server_name* as a case-insensitive substring of the
    advertised name, so a short slug works fine.

    Raises:
        ImportError:  ``zeroconf`` is not installed.
        RuntimeError: No matching server found within *timeout* seconds.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        raise ImportError(
            "Install 'zeroconf' to connect by server name:\n"
            "  pip install zeroconf\n"
            "Or connect explicitly: bench.connect(..., host=..., port=...)"
        ) from None

    found: list[tuple[str, int]] = []
    target = server_name.lower()

    class _Listener:
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if not info or not info.addresses:
                return
            svc_name = (
                info.properties.get(b"server_name", b"").decode(errors="replace")
                or name
            )
            if target not in svc_name.lower():
                return
            found.append((socket.inet_ntoa(info.addresses[0]), info.port))

        def remove_service(self, *_: Any) -> None:
            pass

        def update_service(self, *_: Any) -> None:
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, "_sila._tcp.local.", _Listener())
        deadline = time.monotonic() + timeout
        while not found and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        zc.close()

    if not found:
        raise RuntimeError(
            f"No SiLA server matching {server_name!r} found within {timeout:.0f}s. "
            "Check that the server is running and reachable on the network."
        )
    return found[0]


class RxnBenchClient:
    """Session manager for experiment scripts.

    Handles instrument connections, logging, and the at_well() context.
    Does not assume any particular set of instruments - connect what you have.
    """

    def __init__(self, host: str = "localhost") -> None:
        """
        Args:
            host: Default hostname used when connecting instruments without an explicit host.
        """
        self._host = host
        self._instrument_clients: list[SilaClient] = []
        self._lock_holder: Any = None  # instrument that owns the experiment lock

        self._log_file: Any = None
        self._log_writer: Any = None
        self._log_columns: list[str] | None = None
        self._current_well: str | None = None

    def connect(
        self,
        name: str,
        cls: Type,
        *,
        server: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """Connect to a SiLA server and expose the instrument as ``bench.<name>``.

        Pass either ``server`` (discovered automatically via mDNS) or an
        explicit ``host``/``port`` pair.

            bench.connect("gantry", Gantry,  server="rxn-bench-gantry")
            bench.connect("ph",     PHProbe, server="rxn-bench-ph")
            bench.connect("ph",     PHProbe, host="192.168.1.10", port=50052)

        Args:
            name:   Attribute name (e.g. ``"ph"`` -> ``bench.ph``).
            cls:    Instrument class. Must accept a ``SilaClient`` as its only
                    constructor argument.
            server: mDNS server name - matched case-insensitively as a substring.
            host:   Explicit server host. Defaults to the host passed at init.
            port:   Explicit server port. Defaults to 50052.
        """
        if server is not None:
            h, p = _discover_sila_server(server)
        else:
            h = host or self._host
            p = port or 50052 # just the default instrument SiLA port
        sila = SilaClient(h, p, insecure=True)
        self._instrument_clients.append(sila)
        instrument = cls(sila)
        setattr(self, name, instrument)
        if self._lock_holder is None and hasattr(instrument, "acquire_experiment_lock"):
            instrument.acquire_experiment_lock() # aquire a lock on the instrument to prevent other clients from competing for control
            self._lock_holder = instrument

    def check_pause_stop(self) -> None:
        """Check whether the UI has requested a pause or stop.

        Call this between wells (or any long step) to keep the UI responsive.
        It is called automatically by :meth:`at_well`. You can also call it
        manually inside tight loops::

            for well in bench.gantry.get_workspace_wells("plate1"):
                bench.check_pause_stop()
                do_something_long(well)

        Raises:
            ExperimentStopped: If the UI stop button was pressed.
        """
        if self._lock_holder is None:
            return
        while True:
            state = self._lock_holder.get_experiment_state()
            if state == "stop_requested":
                raise ExperimentStopped("Experiment stopped by user.")
            if state != "paused":
                return
            time.sleep(0.5)

    def close(self) -> None:
        if self._lock_holder is not None:
            try:
                self._lock_holder.release_experiment_lock()
            except Exception:
                pass
            self._lock_holder = None
        if self._log_file:
            self._log_file.close()
            self._log_file = self._log_writer = None
        for c in self._instrument_clients:
            c.close()

    def __enter__(self) -> "RxnBenchClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # Motion convenience - requires bench.gantry to be connected
    @contextlib.contextmanager
    def at_well(
        self,
        well: str,
        stabilize: float = 0.0,
        override_unvalidated: bool = False,
    ) -> Generator[None, None, None]:
        """Move to a well, engage the tool, run the body, then disengage.

        Requires a gantry: ``bench.connect("gantry", Gantry, ...)``.

        Also sets the current well so bench.log() includes it automatically::

            for well in bench.gantry.get_workspace_wells("plate1"):
                with bench.at_well(well, stabilize=3):
                    bench.log(ph=bench.ph.read())

        Args:
            well:      Well label, e.g. ``"plate1/A3"``.
            stabilize: Seconds to wait after engaging before the body runs.
            override_unvalidated: Proceed even if the active toolhead's geometry
                is unvalidated (placeholder tip offsets). Only for mock/dev use -
                on real hardware, measure the toolhead instead.
        """
        if not hasattr(self, "gantry"):
            raise RuntimeError(
                "at_well() requires a gantry. "
                "Call bench.connect('gantry', Gantry, server=...) first."
            )
        self.check_pause_stop()
        self._current_well = well
        self.gantry.move_to_well(well, override_unvalidated=override_unvalidated)
        self.gantry.engage_tool()
        if stabilize:
            time.sleep(stabilize)
        try:
            yield
        finally:
            self.gantry.disengage_tool()
            self._current_well = None

    # Logging
    def set_log_output(
        self,
        path: str | pathlib.Path,
        columns: list[str] | None = None,
    ) -> None:
        """Open a CSV file for recording data with bench.log().

        Args:
            path:    File to write. A relative path is resolved against the
                     RXN_BENCH_RESULTS_DIR set by the Experiment Runner (the
                     app's results/ folder) when present, otherwise the current
                     working directory - so bench.set_log_output("results.csv")
                     lands somewhere predictable instead of wherever the app
                     happened to be launched from. Parent dirs are created.
            columns: Column names in order. When omitted, discovered from the
                     first bench.log() call.
        """
        if self._log_file:
            self._log_file.close()

        out = pathlib.Path(path)
        if not out.is_absolute():
            base = os.environ.get("RXN_BENCH_RESULTS_DIR")
            out = (pathlib.Path(base) if base else pathlib.Path.cwd()) / out
        out.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = open(out, "w", newline="", encoding="utf-8")
        print(f"Logging results to {out}", flush=True)
        self._log_columns = list(columns) if columns is not None else None
        self._log_writer = None

        if self._log_columns is not None:
            self._log_writer = csv.DictWriter(
                self._log_file,
                fieldnames=["timestamp"] + self._log_columns,
                extrasaction="ignore",
            )
            self._log_writer.writeheader()
            self._log_file.flush()

    def log(self, **kwargs: Any) -> None:
        """Append one row to the log file with the current timestamp.

        Call :meth:`set_log_output` first to choose a file. Columns are
        discovered from the keyword argument names on the first call::

            bench.log(ph=7.21, temp=22.1)
        """
        if self._log_file is None:
            raise RuntimeError(
                "Call bench.set_log_output('results.csv') before bench.log()."
            )

        if self._current_well is not None and "well" not in kwargs:
            kwargs = {"well": self._current_well, **kwargs}

        if self._log_writer is None:
            self._log_columns = list(kwargs.keys())
            self._log_writer = csv.DictWriter(
                self._log_file,
                fieldnames=["timestamp"] + self._log_columns,
                extrasaction="ignore",
            )
            self._log_writer.writeheader()

        self._log_writer.writerow(
            {
                "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds"),
                **kwargs,
            }
        )
        self._log_file.flush()
