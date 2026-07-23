"""
Instrument strategy classes for RxnBenchClient.

Each class wraps a single SiLA server and exposes the commands for one
instrument type. Attach any of them to a session with bench.connect().

To support a new instrument, follow the same pattern: accept a SilaClient
in __init__ and expose methods that call it::

    from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

    with RxnBenchClient() as bench:
        bench.connect("gantry", Gantry,   server="rxn-bench-gantry")
        bench.connect("ph",     PHProbe,  server="rxn-bench-ph")

        bench.gantry.mount_toolhead("ph_probe")
        for well in bench.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well, stabilize=3):
                bench.log(ph=bench.ph.read())
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Any

import yaml as _yaml
from sila2.client import SilaClient


def _once(prop) -> Any:
    """Subscribe to a SiLA property, take one value, and cancel."""
    sub = prop.subscribe()
    try:
        return next(sub)
    finally:
        sub.cancel()


def _regression_slope(times: list[float], values: list[float]) -> float:
    """Least-squares slope of *values* vs *times*

    Returns 0.0 when the slope is undefined - fewer than two points, or all
    timestamps equal (duplicate/degenerate sampling) - so callers can lean on
    the peak-to-peak range instead of dividing by a zero time span.
    """
    n = len(times)
    if n < 2:
        return 0.0
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    denom = sum((t - mean_t) ** 2 for t in times)
    if denom == 0.0:
        return 0.0
    num = sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values))
    return num / denom


class _StabilityMonitor:
    """Sliding-window endpoint detector for a settling signal.

    A window is only ever evaluated after it is full *and* at least *min_settle*
    seconds have elapsed, so a probe can't be declared stable before it has had
    time to settle. Any window that fails, or a non-finite reading, resets the
    consecutive counter - a single glitch or excursion restarts the streak.
    """

    def __init__(
        self,
        *,
        window: int,
        min_settle: float,
        max_drift: float,
        max_range: float,
        stable_checks: int,
    ) -> None:
        if window < 2:
            raise ValueError("window must be at least 2")
        if stable_checks < 1:
            raise ValueError("stable_checks must be at least 1")
        self._min_settle = min_settle
        self._max_drift = max_drift
        self._max_range = max_range
        self._stable_checks = stable_checks
        self._times: deque[float] = deque(maxlen=window)
        self._values: deque[float] = deque(maxlen=window)
        self._window = window
        self._consecutive = 0

    def update(self, elapsed: float, value: float) -> bool:
        """Feed one sample; return True once the signal is considered stable.

        Args:
            elapsed: Seconds since the measurement started (the regression's
                time axis). Non-finite values are ignored.
            value:   Latest reading; NaN/inf readings break the stable streak.
        """
        if not math.isfinite(value):
            self._consecutive = 0
            return False
        self._times.append(elapsed)
        self._values.append(value)
        if len(self._values) < self._window or elapsed < self._min_settle:
            return False
        if abs(self.slope()) <= self._max_drift and self.ptp() <= self._max_range:
            self._consecutive += 1
        else:
            self._consecutive = 0
        return self._consecutive >= self._stable_checks

    def slope(self) -> float:
        """Regression drift (value/second) across the current window."""
        return _regression_slope(list(self._times), list(self._values))

    def ptp(self) -> float:
        """Peak-to-peak range (value) across the current window."""
        return max(self._values) - min(self._values) if self._values else 0.0

    def mean(self) -> float:
        """Mean value of the current window - the settled measurement."""
        return sum(self._values) / len(self._values)


class PHStabilityTimeout(TimeoutError):
    """Raised when :meth:`PHProbe.read_stable` times out before settling.

    The best (latest valid) reading and the window's final drift/range are
    preserved as attributes so a caller that wants a best-effort value can
    recover it (``except PHStabilityTimeout as exc: exc.reading``). Subclassing
    :class:`TimeoutError` keeps existing ``except TimeoutError`` handlers working.
    """

    def __init__(self, *, reading: float, elapsed: float, slope: float, ptp: float) -> None:
        self.reading = reading
        self.elapsed = elapsed
        self.slope = slope
        self.ptp = ptp
        super().__init__(
            f"pH did not stabilize within {elapsed:.0f}s "
            f"(last reading {reading:.3f}, drift {slope:+.4f} pH/s, "
            f"range {ptp:.3f} pH)"
        )


def _well_labels(rows: int, cols: int) -> list[str]:
    return [f"{chr(65 + r)}{c + 1}" for r in range(rows) for c in range(cols)]


class Gantry:
    """XYZ motion platform. Attach via bench.connect("gantry", Gantry, server=...).

    Examples::

        bench.connect("gantry", Gantry, server="rxn-bench-gantry")

        bench.gantry.mount_toolhead("ph_probe")
        bench.gantry.move_to_well("plate1/A3")
        bench.gantry.engage_tool()
        bench.gantry.disengage_tool()
        bench.gantry.save_and_park()

        wells = bench.gantry.get_workspace_wells("plate1")
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the gantry server.
        """
        self._g = sila
        self._token = ""  # experiment lock token; set by acquire_experiment_lock()

    def get_workspace_yaml(self) -> str:
        """Return raw YAML of the active workspace."""
        return self._g.Gantry.GetWorkspaceYaml()[0]

    def load_workspace_yaml(
        self,
        content: str | None = None,
        *,
        if_empty: bool = False,
    ) -> None:
        """Load a workspace from a YAML string.

        Pass ``None`` to use whatever workspace is already active on the server
        (raises if none is loaded). Pass ``if_empty=True`` to load only when
        the server has nothing loaded yet.
        """
        if content is None:
            if not self.get_workspace_yaml():
                raise RuntimeError(
                    "No workspace is loaded on the gantry server. "
                    "Load one in the UI or pass a YAML string."
                )
            return
        if if_empty and self.get_workspace_yaml():
            return
        self._g.Gantry.LoadWorkspaceYaml(Content=content, Token=self._token)

    def load_workspace(self, name: str) -> None:
        """Load a named workspace from the server's bundled definitions."""
        self._g.Gantry.SetWorkspace(Name=name, Token=self._token)

    def list_workspaces(self) -> list[str]:
        text = self._g.Gantry.ListWorkspaces()[0]
        return [w for w in text.splitlines() if w]

    def get_labware(self) -> dict:
        """Return the server's labware definitions as ``{plate_type: geometry dict}``.

        The gantry server is the single source of truth for plate geometry
        (rows, columns, spacing_mm, a1 offsets, footprint).
        """
        return _yaml.safe_load(self._g.Gantry.GetLabware()[0]) or {}

    def get_workspace_wells(
        self,
        plate_id: str | None = None,
        *,
        plate_grids: dict[str, tuple[int, int]] | None = None,
    ) -> list[str]:
        """Return every well in the loaded workspace as ``'plate_id/well'`` strings.

        Plate dimensions come from the server's labware definitions
        (see :meth:`get_labware`), so any plate type installed on the server
        works without client-side registration.

        Args:
            plate_id:    Limit results to one plate (e.g. ``"plate1"``).
            plate_grids: Optional ``{plate_type: (rows, cols)}`` overrides.

        Raises:
            RuntimeError: No workspace is loaded.
            ValueError:   Unknown plate type.
        """
        grids = {name: (spec["rows"], spec["columns"]) for name, spec in self.get_labware().items()}
        grids.update(plate_grids or {})
        raw = self.get_workspace_yaml()
        if not raw:
            raise RuntimeError(
                "No workspace is loaded. Load one in the UI or call load_workspace_yaml()."
            )
        data = _yaml.safe_load(raw)
        wells: list[str] = []
        for plate in data.get("plates", []):
            pid = plate["id"]
            ptype = plate["plate_type"]
            if plate_id is not None and pid != plate_id:
                continue
            if ptype not in grids:
                raise ValueError(
                    f"Unknown plate type {ptype!r} on plate {pid!r}. "
                    f"Pass plate_grids={{'{ptype}': (rows, cols)}} to register it."
                )
            rows, cols = grids[ptype]
            wells.extend(f"{pid}/{lbl}" for lbl in _well_labels(rows, cols))
        return wells

    def set_toolhead(self, name: str) -> None:
        """Switch the active toolhead - a pure software change.

        Mount confirmations are per-head and survive switching, so alternating
        between two heads that were each confirmed once (mount_toolhead, or the
        UI at setup) needs no operator interaction mid-script::

            bench.gantry.mount_toolhead("ph_probe")   # confirm once at setup
            bench.gantry.mount_toolhead("pipette")    # confirm once at setup
            ...
            bench.gantry.set_toolhead("ph_probe")     # switch freely mid-run
            bench.gantry.set_toolhead("pipette")
        """
        self._g.Gantry.SetToolhead(Name=name, Token=self._token)

    def confirm_toolhead_mounted(self) -> None:
        """Confirm the *active* toolhead is physically mounted (idempotent)."""
        self._g.Gantry.ConfirmToolheadMounted(Token=self._token)

    def mount_toolhead(self, name: str) -> None:
        """Activate a toolhead and confirm it is physically mounted.

        Idempotent: re-confirming an already-confirmed head is a no-op on the
        server (and does not invalidate homing), so calling this at script
        startup for heads the operator already confirmed is safe.
        """
        self._g.Gantry.SetToolhead(Name=name, Token=self._token)
        self._g.Gantry.ConfirmToolheadMounted(Token=self._token)

    def clear_toolhead_mounted(self) -> None:
        self._g.Gantry.ClearToolheadMounted(Token=self._token)

    def list_toolheads(self) -> list[tuple[str, str]]:
        text = self._g.Gantry.ListToolheads()[0]
        return [
            (p[0].strip(), p[1].strip())
            for line in text.splitlines()
            if len(p := line.split("|", 1)) == 2
        ]

    def move_to(self, x: float, y: float, z: float) -> None:
        self._g.Gantry.MoveTo(X=x, Y=y, Z=z, Token=self._token)

    def move_to_well(self, label: str, override_unvalidated: bool = False) -> None:
        self._g.Gantry.MoveToWell(
            Label=label, OverrideUnvalidated=override_unvalidated, Token=self._token
        )

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self._g.Gantry.Jog(Dx=dx, Dy=dy, Dz=dz, Token=self._token)

    def shake(
        self,
        *,
        amplitude: float = 2.0,
        cycles: int = 10,
        axis: str = "y",
    ) -> None:
        """Oscillate the toolhead can be useful too fling off droplets on toolheads.

        Jogs +/- *amplitude* mm along *axis* for *cycles* round trips and ends
        back at the starting position. Handy after lifting the pH probe clear of
        a well to shake loose water before the next reading, cutting carryover.

        The tip must already be clear of labware: the shake happens at the
        current position, so raise or disengage the tool first.

        Args:
            amplitude: Half-stroke of each oscillation in mm (> 0).
            cycles:    Number of back-and-forth round trips (>= 1).
            axis:      Axis to shake along - "x", "y", or "z".
        """
        if amplitude <= 0.0:
            raise ValueError("amplitude must be positive")
        if cycles < 1:
            raise ValueError("cycles must be at least 1")
        deltas = {
            "x": (amplitude, 0.0, 0.0),
            "y": (0.0, amplitude, 0.0),
            "z": (0.0, 0.0, amplitude),
        }
        try:
            dx, dy, dz = deltas[axis.lower()]
        except KeyError:
            raise ValueError(f"axis must be 'x', 'y', or 'z', got {axis!r}") from None
        for _ in range(cycles):
            self.jog(dx=dx, dy=dy, dz=dz)
            self.jog(dx=-dx, dy=-dy, dz=-dz)

    def engage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = _once(self._g.Gantry.ToolheadInfo).ZEngage
        self._g.Gantry.EngageTool(Depth=depth, Token=self._token)

    def disengage_tool(self, depth: float | None = None) -> None:
        if depth is None:
            depth = _once(self._g.Gantry.ToolheadInfo).ZEngage
        self._g.Gantry.DisengageTool(Depth=depth, Token=self._token)

    def get_position(self) -> tuple[float, float, float]:
        pos = _once(self._g.Gantry.Position)
        return pos.X, pos.Y, pos.Z

    def get_limits(self) -> str:
        return self._g.Gantry.GetLimits()[0]

    def save_and_park(self) -> None:
        self._g.Gantry.SaveAndPark(Token=self._token)

    def acquire_experiment_lock(self) -> None:
        """Claim the experiment lock; all other clients' motion commands are rejected.

        The lock is acquired automatically by :class:`RxnBenchClient` on connect and
        released when the session closes. Only one client can hold the lock at a time.
        The server returns a secret token, which this instrument attaches to every
        subsequent motion/toolhead/workspace command so they pass the backend's
        lock gate; manual UI commands (no token) are rejected until release.
        """
        self._token = self._g.Gantry.AcquireExperimentLock()[0]

    def release_experiment_lock(self) -> None:
        """Release the experiment lock so another client may connect."""
        self._g.Gantry.ReleaseExperimentLock(Token=self._token)
        self._token = ""

    def force_release_experiment_lock(self) -> None:
        """Forcibly clear a stranded experiment lock (no token required).

        Recovery for when a previous script died without releasing - e.g. a
        killed process. Only use when you are sure no script is running.
        """
        self._g.Gantry.ForceReleaseExperimentLock()
        self._token = ""

    def get_experiment_state(self) -> str:
        """Return the current experiment state string (e.g. ``'running'``, ``'paused'``, ``'stop_requested'``)."""
        return self._g.Gantry.GetExperimentState()[0]


class PHProbe:
    """pH probe instrument. Attach via bench.connect("ph", PHProbe, server=...).

    Examples::

        bench.connect("ph", PHProbe, server="rxn-bench-ph")

        ph = bench.ph.read()                           # single reading
        ph = bench.ph.read_avg(n=5)                    # average over 5 readings
        ph = bench.ph.read_stable()                    # wait for probe to settle
        ph = bench.ph.wait_for(above=7.0, timeout=120) # block until threshold
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the pH sensor server.
        """
        self._p = sila

    def read(self) -> float:
        """Single pH reading."""
        return _once(self._p.PHSensor.Ph)

    def read_avg(self, n: int = 5, interval: float = 1.0) -> float:
        """Average of *n* readings taken *interval* seconds apart."""
        readings = [self.read()]
        for _ in range(n - 1):
            time.sleep(interval)
            readings.append(self.read())
        return sum(readings) / len(readings)

    def read_stable(
        self,
        *,
        window: int = 5,
        min_settle: float = 5.0,
        max_drift: float = 0.002,
        max_range: float = 0.02,
        stable_checks: int = 3,
        timeout: float = 300.0,
        interval: float = 1.0,
    ) -> float:
        """Wait for the probe to settle, then return the settled pH.

        A reading is taken every
        *interval* seconds (the probe streams at ~1 Hz) into a rolling *window* of
        the most recent readings. Once the window is full and at least *min_settle*
        seconds have elapsed, each new window is scored on two criteria:

        Args:
            window:        Number of recent readings in the rolling window (>= 2).
            min_settle:    Minimum seconds before any window may be called stable.
            max_drift:     Max absolute regression slope (pH/second) to count stable.
            max_range:     Max peak-to-peak spread (pH) to count stable.
            stable_checks: Consecutive passing windows required (>= 1).
            timeout:       Give up after this many seconds without settling.
            interval:      Seconds between readings (~1.0 for the 1 Hz stream).

        Returns:
            The mean pH of the final settled window.

        Raises:
            PHStabilityTimeout: *timeout* elapsed before the probe settled. The
                best (latest valid) reading is preserved on the exception.
        """
        monitor = _StabilityMonitor(
            window=window,
            min_settle=min_settle,
            max_drift=max_drift,
            max_range=max_range,
            stable_checks=stable_checks,
        )
        start = time.monotonic()
        last_valid = math.nan
        while True:
            value = self.read()
            elapsed = time.monotonic() - start
            if math.isfinite(value):
                last_valid = value
            if monitor.update(elapsed, value):
                return monitor.mean()
            if elapsed >= timeout:
                raise PHStabilityTimeout(
                    reading=last_valid,
                    elapsed=elapsed,
                    slope=monitor.slope(),
                    ptp=monitor.ptp(),
                )
            time.sleep(interval)

    def wait_for(
        self,
        *,
        above: float | None = None,
        below: float | None = None,
        timeout: float = 300.0,
        interval: float = 5.0,
    ) -> float:
        """Block until pH crosses a threshold, then return the reading.

        ph = bench.ph.wait_for(above=7.0, timeout=120)
        ph = bench.ph.wait_for(below=5.0)
        """
        if above is None and below is None:
            raise ValueError("Specify above= or below= (or both).")
        deadline = time.monotonic() + timeout
        while True:
            ph = self.read()
            if (above is None or ph > above) and (below is None or ph < below):
                return ph
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"pH did not reach the target condition within {timeout:.0f}s "
                    f"(last reading: {ph:.2f})"
                )
            time.sleep(interval)

    def calibrate(self, point: str, value: float) -> None:
        """Calibrate the probe at a known buffer.

        Args:
            point: One of ``"mid"``, ``"low"``, ``"high"``, or ``"clear"``.
            value: Known pH of the calibration buffer.
        """
        self._p.PHSensor.Calibrate(Point=point, Value=value)

    def set_temperature(self, celsius: float) -> None:
        """Set the temperature-compensation value used when computing pH.

        The probe assumes 25 C by default; set this to the actual buffer or
        sample temperature before calibrating or reading for accurate results.
        """
        self._p.PHSensor.SetTemperature(Temperature=celsius)


class Camera:
    """Webcam/machine-vision camera. Attach via bench.connect("camera", Camera, server=...).

    Examples::

        bench.connect("camera", Camera, server="rxn-bench-camera")

        image_bytes = bench.camera.snapshot()      # most recent captured frame
        bench.camera.save_snapshot("well_a1.jpg")   # capture and write to disk
        bench.camera.set_capture_interval(10.0)     # capture every 10s instead
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the camera server.
        """
        self._c = sila

    def snapshot(self) -> bytes:
        """Return the most recently captured frame as JPEG-encoded bytes."""
        return _once(self._c.Camera.LatestImage)

    def save_snapshot(self, path: str) -> None:
        """Capture the current frame and write it to a local file."""
        with open(path, "wb") as f:
            f.write(self.snapshot())

    def set_capture_interval(self, seconds: float) -> None:
        """Change how often the server captures (and archives) a new frame."""
        self._c.Camera.SetCaptureInterval(Seconds=seconds)
