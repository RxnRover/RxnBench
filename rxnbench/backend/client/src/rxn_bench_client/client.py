"""
Blocking Python client for Rxn Bench SiLA servers.

Intended for use in experiment scripts run on the backend machine.

auto-discovers and connects the built-in instrument types (see :mod:`rxn_bench_client.devices`), no
``bench.connect(...)`` calls needed::

    from rxn_bench_client import RxnBenchClient

    with RxnBenchClient() as bench:
        bench.set_log_output("results.csv")
        bench.devices.gantry.mount_toolhead("ph_probe")

        for well in bench.devices.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well, stabilize=3):
                bench.log(ph=bench.devices.ph.read())

    # leaving the `with` block parks a connected gantry automatically,
    # whether the script finished, was stopped, or raised

Explicit usage - for a custom instrument, an ambiguous network (more than one
matching server), or just being explicit about host/port::

    from rxn_bench_client import RxnBenchClient, PHProbe

    with RxnBenchClient() as bench:
        bench.connect("ph",          PHProbe,       server="rxn-bench-ph")
        bench.connect("spectrometer", Spectrometer, server="rxn-bench-spec")

        bench.log(ph=bench.ph.read(), abs600=bench.spectrometer.read(600))

Both styles can be mixed freely in the same script, and both end up on
``bench.<name>`` either way.
"""

from __future__ import annotations

import contextlib
import csv
import datetime
import json
import os
import pathlib
import re
import shutil
import socket
import time
from typing import Any, Generator, Iterable, Type

from sila2.client import SilaClient

from .devices import DeviceNamespace
from .workflows import WorkflowRunner


class ExperimentStopped(Exception):
    """Raised by check_pause_stop() when the UI stop button has been pressed."""


def _next_available_path(path: pathlib.Path) -> pathlib.Path:
    """Return *path*, or the first ``<stem>_<n><suffix>`` that doesn't exist yet.

    Used so a re-run never silently overwrites a previous run's results.
    """
    if not path.exists():
        return path
    n = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_filename(s: str) -> str:
    """Replace characters that don't belong in a filename (e.g. ``/`` in a
    step_id like ``"well:24-well4/A1"``) with ``_``."""
    return _UNSAFE_FILENAME_CHARS.sub("_", s)


class _CameraAwareWorkflow:
    """Wraps a WorkflowRunner so bench.workflow.step() automatically calls
    bench.snapshot() on completion and on failure, and tags any snapshot
    taken during the step with its step_id - lives here rather than in
    WorkflowRunner since that stays capability-agnostic. Every other method
    just passes through unchanged.
    """

    def __init__(self, bench: "RxnBenchClient", runner: WorkflowRunner) -> None:
        self._bench = bench
        self._runner = runner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runner, name)

    @contextlib.contextmanager
    def step(
        self,
        step_id: str,
        *,
        devices: Iterable[str] = (),
        idempotent: bool = False,
        confirm_retry: bool = False,
    ) -> Generator[None, None, None]:
        with self._runner.step(
            step_id, devices=devices, idempotent=idempotent, confirm_retry=confirm_retry
        ):
            prev_step = self._bench._current_workflow_step
            self._bench._current_workflow_step = step_id
            try:
                try:
                    yield
                except Exception:
                    self._bench.snapshot("failed")
                    raise
                else:
                    self._bench.snapshot("done")
            finally:
                self._bench._current_workflow_step = prev_step


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
        self._instruments: list[Any] = []  # every wrapped instrument, in connect()/_attach() order
        self._instrument_names: list[str] = []  # parallel to _instruments - for the experiment index
        self._lock_holder: Any = None  # instrument that owns the experiment lock
        self.devices = DeviceNamespace(self)

        self._log_file: Any = None
        self._log_writer: Any = None
        self._log_columns: list[str] | None = None
        self._current_well: str | None = None
        self._workflow: WorkflowRunner | None = None

        self._experiment_dir: pathlib.Path | None = None
        self._experiment_script: str | None = None
        self._experiment_started: str | None = None
        self._current_workflow_step: str | None = None

    def _attach(self, name: str, cls: Type, sila: SilaClient) -> None:
        """Wrap an already-connected SilaClient and expose it as ``bench.<name>``.

        Shared by :meth:`connect` (explicit host/port/server) and
        ``bench.devices.<name>`` (auto-discovered) so both paths get
        identical instrument tracking and lock-acquisition behavior.
        """
        self._instrument_clients.append(sila)
        instrument = cls(sila)
        instrument._bench = self  # lets a few instrument methods auto-snapshot; see instruments/_util.py
        setattr(self, name, instrument)
        self._instruments.append(instrument)
        self._instrument_names.append(name)
        if self._lock_holder is None and hasattr(instrument, "acquire_experiment_lock"):
            instrument.acquire_experiment_lock() # aquire a lock on the instrument to prevent other clients from competing for control
            self._lock_holder = instrument

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
        explicit ``host``/``port`` pair. For the four built-in instrument
        types, ``bench.devices.<name>`` usually means this never needs to be
        called explicitly - see the module docstring.

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
        self._attach(name, cls, sila)

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

    def close(self, *, failed: bool = False) -> None:
        """Park a connected gantry, release the experiment lock, and close up.

        Any connected instrument with a ``save_and_park()`` (i.e. a gantry) is
        parked - moved to its home corner, homing state saved - before the
        lock is released. This runs unconditionally, whatever the reason the
        session is ending: normal completion, a manual stop, or an unhandled
        exception, so a killed or failed run never leaves the gantry's saved
        homing state stale enough to need a manual re-home.

        Args:
            failed: Record the experiment (if :meth:`start_experiment` was
                called) as "failed" rather than "completed" in
                ``experiment.json``. Set automatically by ``__exit__`` when
                the ``with`` block raised - not something a script normally
                passes itself.
        """
        for inst in self._instruments:
            save_and_park = getattr(inst, "save_and_park", None)
            if callable(save_and_park):
                try:
                    save_and_park()
                except Exception:
                    pass
        if self._lock_holder is not None:
            try:
                self._lock_holder.release_experiment_lock()
            except Exception:
                pass
            self._lock_holder = None
        if self._log_file:
            self._log_file.close()
            self._log_file = self._log_writer = None
        if self._workflow is not None:
            self._workflow.close()
            self._workflow = None
        if self._experiment_dir is not None:
            self._write_experiment_index(status="failed" if failed else "completed")
        for c in self._instrument_clients:
            c.close()

    def __enter__(self) -> "RxnBenchClient":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *_: Any) -> None:
        self.close(failed=exc_type is not None)

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
                     If the resolved file already exists (e.g. a previous run
                     used the same name), ``_1``, ``_2``, ... is appended to
                     the stem instead of overwriting it.
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
        out = _next_available_path(out)
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

        A row that can't actually be written (e.g. the results folder is on a
        network share that just dropped) is skipped with a printed warning
        instead of raising - a logging hiccup shouldn't take down an
        otherwise-healthy experiment run.
        """
        if self._log_file is None:
            raise RuntimeError(
                "Call bench.set_log_output('results.csv') before bench.log()."
            )

        if self._current_well is not None and "well" not in kwargs:
            kwargs = {"well": self._current_well, **kwargs}

        try:
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
        except OSError as e:
            print(f"[bench.log] Could not write log row, skipping: {e}", flush=True)

    # Workflow / resume tracking
    def set_workflow_output(
        self,
        path: str | pathlib.Path,
        *,
        restart: bool | None = None,
    ) -> None:
        """Configure the manifest file used by :attr:`workflow`.

        Args:
            path: Where to persist step status. Resolves like
                :meth:`set_log_output` - don't prefix with ``"results/"``.
                Must be a *stable* name (no timestamp): resume relies on
                pointing two runs at the same path, and the Experiment
                Runner's resume prompt looks for exactly
                ``f"logs/{Path(script).stem}_workflow.jsonl"``::

                    bench.set_workflow_output(f"logs/{Path(__file__).stem}_workflow.jsonl")

                    for well in bench.workflow.remaining(wells, key=lambda w: f"well:{w}"):
                        with bench.workflow.step(f"well:{well}", devices=["gantry", "ph"]):
                            with bench.at_well(well, stabilize=3):
                                bench.log(ph=bench.ph.read())
            restart: Force starting over (True) or resuming (False),
                regardless of what's on disk. Defaults to checking the
                ``RXN_BENCH_WORKFLOW_RESTART`` env var - how the Experiment
                Runner's resume prompt reaches a launched script.
        """
        if restart is None:
            restart = os.environ.get("RXN_BENCH_WORKFLOW_RESTART") == "1"
        if self._workflow is not None:
            self._workflow.close()
        self._workflow = WorkflowRunner(path, restart=restart)

    @property
    def workflow(self) -> WorkflowRunner:
        """The active :class:`WorkflowRunner`. Call :meth:`set_workflow_output` first.

        ``.step()`` automatically saves a camera snapshot per step (and on
        failure) whenever :attr:`camera` is attached and
        :meth:`start_experiment` has been called - no extra code needed.
        """
        if self._workflow is None:
            raise RuntimeError(
                "Call bench.set_workflow_output('results/my_workflow.jsonl') "
                "before bench.workflow."
            )
        return _CameraAwareWorkflow(self, self._workflow)

    # Experiment folder
    @property
    def experiment_dir(self) -> pathlib.Path | None:
        """The folder created by :meth:`start_experiment`, or None if it wasn't called."""
        return self._experiment_dir

    def start_experiment(self, script_path: str | pathlib.Path) -> pathlib.Path:
        """Create a self-contained results folder for this run.

        Makes ``<script-stem>_<timestamp>/`` under the results location
        (same resolution as :meth:`set_log_output`), and points
        :meth:`set_log_output` at ``results.csv`` inside it by default (call
        it again afterward for a different name in the same folder). Also
        copies *script_path* in and, if a gantry is attached, saves the
        active workspace as ``workspace.yaml``. Writes an ``experiment.json``
        index now, updated by :meth:`close`.

        A *new* folder is created every call - unlike
        :meth:`set_workflow_output`, whose manifest deliberately stays at a
        separate, stable path so resume still works across fresh folders.

        Args:
            script_path: Typically ``__file__`` - identifies both the folder
                name and the file copied into it::

                    bench.start_experiment(__file__)

        Returns:
            The created experiment directory (also available as
            :attr:`experiment_dir`).
        """
        script_path = pathlib.Path(script_path)
        base = os.environ.get("RXN_BENCH_RESULTS_DIR")
        root = pathlib.Path(base) if base else pathlib.Path.cwd()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = root / f"{script_path.stem}_{ts}"
        folder.mkdir(parents=True, exist_ok=True)

        self._experiment_dir = folder
        self._experiment_script = script_path.name
        self._experiment_started = datetime.datetime.now().isoformat(timespec="milliseconds")

        self.set_log_output(folder / "results.csv")

        try:
            shutil.copy2(script_path, folder / script_path.name)
        except OSError as e:
            print(f"[bench.start_experiment] Could not copy script into folder: {e}", flush=True)

        gantry = getattr(self, "gantry", None)
        if gantry is not None:
            try:
                yaml_text = gantry.get_workspace_yaml()
                if yaml_text:
                    (folder / "workspace.yaml").write_text(yaml_text, encoding="utf-8")
            except Exception as e:
                print(f"[bench.start_experiment] Could not save workspace snapshot: {e}", flush=True)

        self._write_experiment_index(status="running")
        return folder

    def _write_experiment_index(self, *, status: str) -> None:
        data = {
            "script": self._experiment_script,
            "started": self._experiment_started,
            "finished": None if status == "running" else
                datetime.datetime.now().isoformat(timespec="milliseconds"),
            "status": status,
            "devices": list(self._instrument_names),
        }
        (self._experiment_dir / "experiment.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def snapshot(self, label: str = "") -> None:
        """Save a camera snapshot (+ gantry position, if attached), logged
        to experiment_dir/images/images.jsonl.

        Call this anywhere - not just automatically at step boundaries - for
        an image per physical action, e.g.::

            with bench.workflow.step(f"well:{well}"):
                with bench.at_well(well):
                    bench.snapshot("engaged")
                    ph = bench.ph.read()
                bench.snapshot("disengaged")

        Tagged with the active bench.workflow.step()'s step_id, if any.
        No-ops silently unless both :attr:`camera` is attached and
        :meth:`start_experiment` has been called - never raises, since a
        camera problem must never break the actual experiment.

        Args:
            label: Freeform tag for this moment (e.g. ``"engaged"``,
                ``"pre-dispense"``). Optional.
        """
        camera = getattr(self, "camera", None)
        if camera is None or self._experiment_dir is None:
            return
        images_dir = self._experiment_dir / "images"
        try:
            images_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            parts = [p for p in (self._current_workflow_step, label) if p]
            prefix = _safe_filename("_".join(parts)) + "_" if parts else ""
            filename = f"{prefix}{ts}.jpg"
            camera.save_snapshot(str(images_dir / filename))

            position = None
            gantry = getattr(self, "gantry", None)
            if gantry is not None:
                try:
                    x, y, z = gantry.get_position()
                    position = {"x": x, "y": y, "z": z}
                except Exception:
                    pass  # image is still worth having without a position

            row = {
                "image": filename,
                "step_id": self._current_workflow_step,
                "label": label or None,
                "position": position,
                "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds"),
            }
            with open(images_dir / "images.jsonl", "a", encoding="utf-8") as f:
                json.dump(row, f)
                f.write("\n")
        except Exception as e:
            print(f"[bench.snapshot] Could not save snapshot: {e}", flush=True)
