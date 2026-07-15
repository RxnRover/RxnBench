"""Tests for the Gantry/PHProbe instrument wrappers.

A fake SiLA client stands in for the live server: it records every command
call (name + kwargs) so tests can assert the lock token is attached, and
serves canned labware/workspace responses for the well-enumeration logic.
"""
import textwrap

import pytest

import rxn_bench_client.instruments as instruments_module
from rxn_bench_client.instruments import Camera, Gantry, PHProbe, _well_labels

_LABWARE_YAML = textwrap.dedent("""\
    96_well_standard:
      rows: 8
      columns: 12
      spacing_mm: 9.0
    24_well_standard:
      rows: 4
      columns: 6
      spacing_mm: 19.3
""")

_WORKSPACE_YAML = textwrap.dedent("""\
    name: bench
    calibration_reference_well: plate1/A1
    plates:
      - id: plate1
        plate_type: 96_well_standard
        origin: {x: 50.0, y: 30.0, z: 15.0}
      - id: plate2
        plate_type: 24_well_standard
        origin: {x: 200.0, y: 30.0, z: 15.0}
""")


class _FakeGantryFeature:
    """Stands in for sila_client.Gantry: records calls, returns canned data."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.workspace_yaml = _WORKSPACE_YAML

    def _rec(self, name, **kw):
        self.calls.append((name, kw))

    def kwargs_of(self, name) -> dict:
        return next(kw for n, kw in self.calls if n == name)

    # Lock
    def AcquireExperimentLock(self):
        self._rec("AcquireExperimentLock")
        return ("tok-secret",)

    def ReleaseExperimentLock(self, **kw):
        self._rec("ReleaseExperimentLock", **kw)

    # Motion
    def MoveTo(self, **kw):
        self._rec("MoveTo", **kw)

    def MoveToWell(self, **kw):
        self._rec("MoveToWell", **kw)

    def Jog(self, **kw):
        self._rec("Jog", **kw)

    def EngageTool(self, **kw):
        self._rec("EngageTool", **kw)

    def DisengageTool(self, **kw):
        self._rec("DisengageTool", **kw)

    def SaveAndPark(self, **kw):
        self._rec("SaveAndPark", **kw)

    # Toolheads
    def SetToolhead(self, **kw):
        self._rec("SetToolhead", **kw)

    def ConfirmToolheadMounted(self, **kw):
        self._rec("ConfirmToolheadMounted", **kw)

    def ClearToolheadMounted(self, **kw):
        self._rec("ClearToolheadMounted", **kw)

    def ListToolheads(self):
        return ("ph_probe|Atlas pH Probe\npipette|Pipette v2\nmalformed-line",)

    # Workspace / labware
    def SetWorkspace(self, **kw):
        self._rec("SetWorkspace", **kw)

    def LoadWorkspaceYaml(self, **kw):
        self._rec("LoadWorkspaceYaml", **kw)

    def GetWorkspaceYaml(self):
        return (self.workspace_yaml,)

    def GetLabware(self):
        return (_LABWARE_YAML,)

    def ListWorkspaces(self):
        return ("bench_default\ncalibration\n",)


class _FakeSila:
    def __init__(self):
        self.Gantry = _FakeGantryFeature()


@pytest.fixture
def feature():
    return _FakeGantryFeature()


@pytest.fixture
def gantry(feature):
    sila = _FakeSila()
    sila.Gantry = feature
    return Gantry(sila)


# Experiment-lock token plumbing

def test_acquire_lock_stores_token_and_attaches_it_to_commands(gantry, feature):
    gantry.acquire_experiment_lock()
    gantry.move_to(1.0, 2.0, 3.0)
    gantry.jog(dx=5.0)
    gantry.move_to_well("plate1/A3")
    gantry.save_and_park()
    for cmd in ("MoveTo", "Jog", "MoveToWell", "SaveAndPark"):
        assert feature.kwargs_of(cmd)["Token"] == "tok-secret"


def test_commands_send_empty_token_before_lock_is_acquired(gantry, feature):
    gantry.jog(dx=1.0)
    assert feature.kwargs_of("Jog")["Token"] == ""


def test_release_lock_sends_token_then_clears_it(gantry, feature):
    gantry.acquire_experiment_lock()
    gantry.release_experiment_lock()
    assert feature.kwargs_of("ReleaseExperimentLock")["Token"] == "tok-secret"
    assert gantry._token == ""


def test_mount_toolhead_sets_then_confirms_with_token(gantry, feature):
    gantry.acquire_experiment_lock()
    gantry.mount_toolhead("ph_probe")
    assert feature.kwargs_of("SetToolhead") == {"Name": "ph_probe", "Token": "tok-secret"}
    assert feature.kwargs_of("ConfirmToolheadMounted")["Token"] == "tok-secret"


# Server-sourced labware and well enumeration

def test_well_labels_row_major():
    assert _well_labels(2, 3) == ["A1", "A2", "A3", "B1", "B2", "B3"]


def test_get_labware_parses_server_yaml(gantry):
    labware = gantry.get_labware()
    assert labware["96_well_standard"]["rows"] == 8
    assert labware["24_well_standard"]["columns"] == 6


def test_get_workspace_wells_uses_server_labware(gantry):
    wells = gantry.get_workspace_wells()
    assert len(wells) == 96 + 24
    assert wells[0] == "plate1/A1"
    assert "plate2/D6" in wells


def test_get_workspace_wells_filters_by_plate_id(gantry):
    wells = gantry.get_workspace_wells("plate2")
    assert len(wells) == 24
    assert all(w.startswith("plate2/") for w in wells)


def test_get_workspace_wells_unknown_plate_type_raises(gantry, feature):
    feature.workspace_yaml = "plates:\n  - {id: x, plate_type: mystery_plate}\n"
    with pytest.raises(ValueError, match="mystery_plate"):
        gantry.get_workspace_wells()


def test_get_workspace_wells_plate_grids_override(gantry, feature):
    feature.workspace_yaml = "plates:\n  - {id: x, plate_type: mystery_plate}\n"
    wells = gantry.get_workspace_wells(plate_grids={"mystery_plate": (2, 2)})
    assert wells == ["x/A1", "x/A2", "x/B1", "x/B2"]


def test_get_workspace_wells_without_workspace_raises(gantry, feature):
    feature.workspace_yaml = ""
    with pytest.raises(RuntimeError, match="No workspace"):
        gantry.get_workspace_wells()


def test_list_toolheads_skips_malformed_lines(gantry):
    assert gantry.list_toolheads() == [
        ("ph_probe", "Atlas pH Probe"),
        ("pipette", "Pipette v2"),
    ]


def test_list_workspaces_drops_blank_lines(gantry):
    assert gantry.list_workspaces() == ["bench_default", "calibration"]


# shake: net-zero oscillation built from paired jogs

def test_shake_oscillates_and_returns_to_origin(gantry, feature):
    gantry.shake(amplitude=1.5, cycles=3, axis="y")
    jogs = [kw for name, kw in feature.calls if name == "Jog"]
    assert len(jogs) == 6  # two half-strokes per cycle
    assert all(j["Dx"] == 0.0 and j["Dz"] == 0.0 for j in jogs)
    assert [j["Dy"] for j in jogs] == [1.5, -1.5, 1.5, -1.5, 1.5, -1.5]
    assert sum(j["Dy"] for j in jogs) == 0.0  # ends where it started


def test_shake_axis_selects_displacement_component(gantry, feature):
    gantry.shake(amplitude=2.0, cycles=1, axis="z")
    out, back = [kw for name, kw in feature.calls if name == "Jog"]
    assert (out["Dx"], out["Dy"], out["Dz"]) == (0.0, 0.0, 2.0)
    assert (back["Dx"], back["Dy"], back["Dz"]) == (0.0, 0.0, -2.0)


def test_shake_carries_experiment_token(gantry, feature):
    gantry.acquire_experiment_lock()
    gantry.shake(cycles=1)
    assert all(kw["Token"] == "tok-secret" for n, kw in feature.calls if n == "Jog")


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"amplitude": 0.0}, "amplitude"),
        ({"cycles": 0}, "cycles"),
        ({"axis": "w"}, "axis"),
    ],
)
def test_shake_rejects_bad_arguments(gantry, kwargs, match):
    with pytest.raises(ValueError, match=match):
        gantry.shake(**kwargs)


# PHProbe convenience readers

class _FakeSubscription:
    def __init__(self, value):
        self._value = value

    def __next__(self):
        return self._value

    def cancel(self):
        pass


class _FakePhProperty:
    """Serves a scripted sequence of pH values, one per subscribe()."""

    def __init__(self, values):
        self._values = list(values)

    def subscribe(self):
        value = self._values.pop(0) if len(self._values) > 1 else self._values[0]
        return _FakeSubscription(value)


class _FakePHSensorFeature:
    def __init__(self, values):
        self.Ph = _FakePhProperty(values)


class _FakePHSila:
    def __init__(self, values):
        self.PHSensor = _FakePHSensorFeature(values)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(instruments_module.time, "sleep", lambda *_a, **_k: None)


def _probe(values):
    return PHProbe(_FakePHSila(values))


def test_read_returns_single_value():
    assert _probe([7.21]).read() == pytest.approx(7.21)


def test_read_avg_averages_n_readings():
    probe = _probe([7.0, 7.2, 7.4])
    assert probe.read_avg(n=3, interval=0) == pytest.approx(7.2)


# --- Endpoint-detection stability logic ------------------------------------
#
# The window/slope/range/consecutive-count math lives in _StabilityMonitor, which
# is fed (elapsed_seconds, pH) samples directly, so these tests exercise it
# without a clock. The read_stable() I/O loop is covered separately below.

_StabilityMonitor = instruments_module._StabilityMonitor
_regression_slope = instruments_module._regression_slope
PHStabilityTimeout = instruments_module.PHStabilityTimeout


def _monitor(**overrides):
    """Default-config monitor: 5-reading window, 5 s settle, 0.002 pH/s drift,
    0.02 pH range, 3 consecutive windows - overridable per test."""
    cfg = dict(window=5, min_settle=5.0, max_drift=0.002, max_range=0.02, stable_checks=3)
    cfg.update(overrides)
    return _StabilityMonitor(**cfg)


def test_stability_accepts_flat_signal():
    # A dead-flat 1 Hz signal settles after the window fills, the settle time
    # passes, and three consecutive windows pass - not before.
    mon = _monitor()
    results = [mon.update(float(t), 7.00) for t in range(8)]
    assert not any(results[:7])            # window+settle+3-in-a-row gate
    assert results[7] is True
    assert mon.mean() == pytest.approx(7.00)


def test_stability_rejects_slow_drift_within_range():
    # +0.004 pH/s creep: over a 4 s window the spread is only 0.016 pH (inside
    # max_range) but the slope exceeds max_drift, so it must never be accepted.
    mon = _monitor()
    stream = [(float(t), 7.00 + 0.004 * t) for t in range(21)]
    assert not any(mon.update(t, v) for t, v in stream)
    assert mon.ptp() <= 0.02               # range criterion is satisfied...
    assert abs(mon.slope()) > 0.002        # ...but the drift criterion is not


def test_stability_rejects_noisy_signal_with_large_range():
    # Alternating 7.00/7.05: the drift averages to ~0 but the 0.05 pH swing
    # blows past max_range, so the range criterion holds it out.
    mon = _monitor()
    stream = [(float(t), 7.00 if t % 2 == 0 else 7.05) for t in range(21)]
    assert not any(mon.update(t, v) for t, v in stream)
    assert abs(mon.slope()) <= 0.002       # drift criterion is satisfied...
    assert mon.ptp() > 0.02                # ...but the range criterion is not


def test_stability_settles_after_initial_drift():
    # A steep ramp that then plateaus at 7.20: not stable while drifting, but
    # once the window is entirely on the plateau it settles on the mean.
    mon = _monitor()
    stream = [(float(t), 7.00 + 0.05 * t) for t in range(6)]        # drift, t=0..5
    stream += [(float(t), 7.20) for t in range(6, 20)]             # plateau
    results = [mon.update(t, v) for t, v in stream]
    assert not any(results[:6])            # unstable through the ramp
    assert results[-1] is True             # eventually settles
    assert mon.mean() == pytest.approx(7.20)


def test_stability_requires_three_consecutive_windows():
    # Two passing windows are not enough; the third consecutive one settles it.
    mon = _monitor()
    for t in range(5):                     # fill window (t=4 is still < min_settle)
        assert mon.update(float(t), 7.00) is False
    assert mon.update(5.0, 7.00) is False   # 1st passing window
    assert mon.update(6.0, 7.00) is False   # 2nd passing window - still short
    assert mon.update(7.0, 7.00) is True    # 3rd consecutive -> settled


def test_stability_streak_resets_on_failing_window():
    # A single out-of-range excursion resets the consecutive count, so the
    # required streak has to be rebuilt from scratch.
    mon = _monitor(window=2, min_settle=0.0)
    assert mon.update(0.0, 7.00) is False   # window not full yet
    assert mon.update(1.0, 7.00) is False   # pass 1
    assert mon.update(2.0, 7.00) is False   # pass 2
    assert mon.update(3.0, 7.30) is False   # excursion fails -> reset (else pass 3)
    assert mon.update(4.0, 7.30) is False   # pass 1 again
    assert mon.update(5.0, 7.30) is False   # pass 2
    assert mon.update(6.0, 7.30) is True    # pass 3 -> settled


def test_stability_ignores_nan_and_resets_streak():
    # A NaN reading is dropped from the window and breaks the stable streak.
    mon = _monitor()
    for t in range(7):
        mon.update(float(t), 7.00)          # streak building; count is 2 by t=6
    assert mon.update(7.0, float("nan")) is False   # dropped + streak reset
    assert mon.update(8.0, 7.00) is False           # count 1 (proves the reset)
    assert mon.update(9.0, 7.00) is False           # count 2
    assert mon.update(10.0, 7.00) is True           # count 3 -> settled


def test_stability_rejects_bad_config():
    with pytest.raises(ValueError, match="window must be at least 2"):
        _monitor(window=1)
    with pytest.raises(ValueError, match="stable_checks must be at least 1"):
        _monitor(stable_checks=0)


def test_regression_slope_handles_degenerate_inputs():
    assert _regression_slope([0.0, 1.0, 2.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert _regression_slope([5.0], [7.0]) == 0.0            # too few points
    assert _regression_slope([2.0, 2.0, 2.0], [7.0, 7.1, 7.2]) == 0.0  # equal times


# --- read_stable() I/O loop ------------------------------------------------


class _StepClock:
    """time.monotonic() stand-in: 0 for the first call (read_stable's start
    marker), then 0, 1, 2, ... nominal seconds - one per reading at 1 Hz."""

    def __init__(self, step: float = 1.0) -> None:
        self._step = step
        self._n = 0

    def __call__(self) -> float:
        n = self._n
        self._n += 1
        return max(0, n - 1) * self._step


def test_read_stable_returns_window_mean_when_settled(monkeypatch):
    monkeypatch.setattr(instruments_module.time, "monotonic", _StepClock())
    assert _probe([7.00]).read_stable() == pytest.approx(7.00)


def test_read_stable_times_out_and_preserves_last_reading(monkeypatch):
    monkeypatch.setattr(instruments_module.time, "monotonic", _StepClock())
    # A steep, never-settling ramp; the timeout fires before stability.
    probe = _probe([7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0])
    with pytest.raises(PHStabilityTimeout) as exc:
        probe.read_stable(timeout=5.0)
    assert exc.value.reading == pytest.approx(9.5)   # best/latest reading kept
    assert exc.value.elapsed == pytest.approx(5.0)


def test_read_stable_timeout_is_a_timeout_error(monkeypatch):
    # Subclassing TimeoutError keeps existing `except TimeoutError` handlers valid.
    monkeypatch.setattr(instruments_module.time, "monotonic", _StepClock())
    with pytest.raises(TimeoutError):
        _probe([4.0, 5.0, 6.0, 7.0, 8.0, 9.0]).read_stable(timeout=5.0)


def test_read_stable_rejects_bad_config():
    with pytest.raises(ValueError, match="window must be at least 2"):
        _probe([7.0]).read_stable(window=1)


def test_read_stable_uses_fresh_state_each_call(monkeypatch):
    # Each call builds its own monitor, so a second measurement isn't polluted
    # by the first.
    probe = _probe([7.00])
    monkeypatch.setattr(instruments_module.time, "monotonic", _StepClock())
    assert probe.read_stable() == pytest.approx(7.00)
    monkeypatch.setattr(instruments_module.time, "monotonic", _StepClock())
    assert probe.read_stable() == pytest.approx(7.00)


def test_wait_for_above_returns_first_crossing():
    probe = _probe([6.5, 6.8, 7.2])
    assert probe.wait_for(above=7.0, interval=0) == pytest.approx(7.2)


def test_wait_for_requires_a_threshold():
    with pytest.raises(ValueError, match="above= or below="):
        _probe([7.0]).wait_for()


def test_wait_for_timeout_raises():
    probe = _probe([7.0])
    with pytest.raises(TimeoutError, match="did not reach"):
        probe.wait_for(below=5.0, timeout=0.0, interval=0)


# Camera

class _FakeImageProperty:
    def __init__(self, image: bytes):
        self._image = image

    def subscribe(self):
        return _FakeSubscription(self._image)


class _FakeCameraFeature:
    def __init__(self, image: bytes):
        self.LatestImage = _FakeImageProperty(image)
        self.set_capture_interval_calls: list[float] = []

    def SetCaptureInterval(self, Seconds):
        self.set_capture_interval_calls.append(Seconds)


class _FakeCameraSila:
    def __init__(self, image: bytes):
        self.Camera = _FakeCameraFeature(image)


def test_snapshot_returns_latest_image_bytes():
    camera = Camera(_FakeCameraSila(b"\xff\xd8\xff\xe0jpegdata"))
    assert camera.snapshot() == b"\xff\xd8\xff\xe0jpegdata"


def test_save_snapshot_writes_bytes_to_file(tmp_path):
    camera = Camera(_FakeCameraSila(b"\xff\xd8\xff\xe0jpegdata"))
    path = tmp_path / "frame.jpg"
    camera.save_snapshot(str(path))
    assert path.read_bytes() == b"\xff\xd8\xff\xe0jpegdata"


def test_set_capture_interval_forwards_seconds():
    sila = _FakeCameraSila(b"x")
    Camera(sila).set_capture_interval(10.0)
    assert sila.Camera.set_capture_interval_calls == [10.0]
