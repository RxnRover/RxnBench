"""
Instrument strategy classes for RxnBenchClient.

Each class wraps a single SiLA server and exposes the commands for one
instrument type. These four are auto-discovered via bench.devices.<name>
(see rxn_bench_client.devices) - bench.connect() also still works, and is
the only option for a custom instrument not in DEVICE_REGISTRY.

To support a new instrument, follow the same pattern: accept a SilaClient
in __init__ and expose methods that call it::

    from rxn_bench_client import RxnBenchClient, Spectrometer

    with RxnBenchClient() as bench:
        bench.connect("spectrometer", Spectrometer, server="rxn-bench-spec")

        bench.devices.gantry.mount_toolhead("ph_probe")
        for well in bench.devices.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well, stabilize=3):
                bench.log(ph=bench.devices.ph.read())
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

        wells = bench.gantry.get_workspace_wells("plate1")

    ``save_and_park()`` moves to the home corner and persists homing state for
    next session; ``RxnBenchClient.close()`` calls it automatically whenever a
    connected gantry's session ends (script finished, stopped, or raised), so
    scripts don't need to call it directly.
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
        amplitude: float = 1.5,
        cycles: int = 12,
        axis: str = "xy",
    ) -> None:
        """Jitter the toolhead to fling off droplets on toolheads.

        Jogs +/- *amplitude* mm for *cycles* round trips, cycling through each
        axis in *axis* in turn (round-robin) rather than oscillating along a
        single axis, and ends back at the starting position. Handy after
        lifting the pH probe clear of a well to shake loose water before the
        next reading, cutting carryover.

        Short, frequent bursts across more than one axis shake harder than one
        long oscillation on a single axis of the same total travel: each jog
        is its own accel/decel burst, so more (shorter) jogs pack more
        direction reversals into the same envelope, and alternating axes flings
        droplets in more than one direction instead of just back and forth.

        The tip must already be clear of labware: the shake happens at the
        current position, so raise or disengage the tool first.

        Args:
            amplitude: Half-stroke of each burst in mm (> 0).
            cycles:    Number of back-and-forth bursts (>= 1), split round-robin
                       across the axes in *axis*.
            axis:      Axis or axes to shake along, any combination of "x", "y",
                       "z" - e.g. "y" for a single axis (the old default) or
                       "xy"/"xyz" to alternate between them each cycle.
        """
        if amplitude <= 0.0:
            raise ValueError("amplitude must be positive")
        if cycles < 1:
            raise ValueError("cycles must be at least 1")
        unit = {
            "x": (1.0, 0.0, 0.0),
            "y": (0.0, 1.0, 0.0),
            "z": (0.0, 0.0, 1.0),
        }
        axis = axis.lower()
        if not axis or any(a not in unit for a in axis):
            raise ValueError(f"axis must only contain 'x', 'y', or 'z', got {axis!r}")
        for i in range(cycles):
            ux, uy, uz = unit[axis[i % len(axis)]]
            dx, dy, dz = ux * amplitude, uy * amplitude, uz * amplitude
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
        window: int = 10,
        min_settle: float = 5.0,
        max_drift: float = 0.002,
        max_range: float = 0.03,
        stable_checks: int = 3,
        timeout: float = 300.0,
        interval: float = 1.0,
    ) -> float:
        # window=10 (not 5): the OLS slope's standard error is sigma/sqrt(Sum (t-tbar)^2),
        # ~sigma/3.2 at window=5 vs ~sigma/9 at window=10. With this probe's measured
        # per-reading noise sigma~=0.007 pH, a 5-sample window puts the slope SE (~0.0022)
        # ABOVE max_drift, so a settled probe fails the drift gate ~35% of the time on
        # noise alone; at window=10 the SE (~0.0008) sits well below it. max_range is 0.03
        # (not 0.02) because peak-to-peak grows with window size (E[ptp]~=3.1*sigma at
        # window=10 ~= 0.021), so the old 0.02 would reject settled windows outright.
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

        Never raises on a timeout: if *timeout* elapses before the probe
        settles, a warning is printed (with the best/latest reading and the
        window's final drift/range) and that best-effort reading is returned
        instead - a slow-to-settle well shouldn't crash an otherwise-healthy
        run.

        Returns:
            The mean pH of the final settled window, or the best (latest
            valid) reading if *timeout* elapsed first.
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
                print(
                    f"WARNING: pH did not stabilize within {elapsed:.0f}s "
                    f"(last reading {last_valid:.3f}, drift {monitor.slope():+.4f} pH/s, "
                    f"range {monitor.ptp():.3f} pH) - using best-effort reading and continuing."
                )
                return last_valid
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


class DosingPump:
    """Peristaltic dosing pump. Attach via bench.connect("pump", DosingPump, server=...).

    Dispense commands return as soon as the pump accepts them - the pump keeps
    running in the background. Use :meth:`dispense_and_wait` (or poll
    :meth:`is_dispensing`) when the script must not continue until the liquid
    is actually delivered.

    Examples::

        bench.connect("pump", DosingPump, server="Dosing Pump")

        bench.pump.dispense_and_wait(5.0)        # 5ml, blocks until delivered
        bench.pump.dose_over_time(50.0, 30.0)    # 50ml spread over 30 min
        bench.pump.set_flow_rate(2.0)            # hold 2 ml/min until stopped
        bench.pump.stop()
        bench.log(dispensed=bench.pump.total_volume())
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the dosing pump server.
        """
        self._p = sila

    # Readings

    def volume_dispensed(self) -> float:
        """Volume delivered by the current or last dispense, in ml."""
        return _once(self._p.DosingPump.VolumeDispensed)

    def is_dispensing(self) -> bool:
        """True while the pump is running."""
        return _once(self._p.DosingPump.Dispensing)

    def total_volume(self) -> float:
        """Net total volume pumped since the last clear, in ml. Reverse subtracts."""
        return self._p.DosingPump.TotalVolume.get()

    def absolute_total_volume(self) -> float:
        """Total volume pumped since the last clear ignoring direction, in ml."""
        return self._p.DosingPump.AbsoluteTotalVolume.get()

    def max_flow_rate(self) -> float:
        """Fastest flow rate in ml/min that :meth:`set_flow_rate` can hold steady.

        Determined after calibration. Not the pump's top speed:
        :meth:`dispense_continuously` runs open-loop at ~105 ml/min, well above
        this. Asking :meth:`set_flow_rate` for more is rejected.
        """
        return self._p.DosingPump.MaxFlowRate.get()

    def pump_voltage(self) -> float:
        """Motor supply voltage in volts."""
        return self._p.DosingPump.PumpVoltage.get()

    # Dispensing

    def dispense(self, volume: float) -> None:
        """Dispense a fixed volume in ml (minimum 0.5). Negative dispenses in reverse.

        Returns as soon as the pump accepts the command.
        """
        self._p.DosingPump.Dispense(Volume=volume)

    def dispense_and_wait(self, volume: float, timeout: float = 600.0,
                          poll: float = 0.5) -> float:
        """Dispense a fixed volume and block until the pump reports it finished.

        Args:
            volume: Volume to dispense in ml. Negative dispenses in reverse.
            timeout: Seconds to wait before giving up.
            poll: Seconds between progress checks.

        Returns:
            The volume actually delivered, in ml.

        Raises:
            TimeoutError: The pump was still running when *timeout* elapsed.
        """
        self.dispense(volume)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_dispensing():
                return self.volume_dispensed()
            time.sleep(poll)
        raise TimeoutError(
            f"Pump still dispensing after {timeout}s (requested {volume}ml, "
            f"delivered {self.volume_dispensed()}ml so far)"
        )

    def dose_over_time(self, volume: float, minutes: float) -> None:
        """Dispense a volume in ml spread evenly over the given number of minutes."""
        self._p.DosingPump.DoseOverTime(Volume=volume, Minutes=minutes)

    def dispense_continuously(self, reverse: bool = False) -> None:
        """Run at maximum rate until stop() is called."""
        self._p.DosingPump.DispenseContinuously(Reverse=reverse)

    def set_flow_rate(self, rate: float, minutes: float = 0.0) -> None:
        """Hold a constant flow rate in ml/min; zero minutes runs until stop()."""
        self._p.DosingPump.SetFlowRate(Rate=rate, Minutes=minutes)

    def stop(self) -> float:
        """Stop dispensing immediately and return the volume delivered, in ml."""
        return self._p.DosingPump.Stop().VolumeDispensed

    def set_paused(self, paused: bool) -> None:
        """Pause or resume the dispense in progress. Idempotent."""
        self._p.DosingPump.SetPaused(Paused=paused)

    def set_inverted(self, inverted: bool) -> None:
        """Flip or unflip the dispensing direction. Retained across power loss."""
        self._p.DosingPump.SetInverted(Inverted=inverted)

    # Totals and calibration

    def clear_total_volume(self) -> None:
        """Reset both total-volume counters to zero."""
        self._p.DosingPump.ClearTotalVolume()

    def calibrate(self, volume: float) -> None:
        """Calibrate against the volume actually delivered by the last dispense, in ml."""
        self._p.DosingPump.Calibrate(Volume=volume)

    def clear_calibration(self) -> None:
        """Erase all stored calibration data."""
        self._p.DosingPump.ClearCalibration()

    def calibration_status(self) -> int:
        """Return 0 uncalibrated, 1 fixed volume, 2 volume over time, or 3 both."""
        return self._p.DosingPump.GetCalibrationStatus().CalibrationStatus
