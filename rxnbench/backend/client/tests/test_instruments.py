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


# ---------------------------------------------------------------------------
# Experiment-lock token plumbing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Server-sourced labware and well enumeration
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# PHProbe convenience readers
# ---------------------------------------------------------------------------

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


def test_read_stable_returns_when_consecutive_readings_agree():
    probe = _probe([7.5, 7.3, 7.29])
    assert probe.read_stable(tolerance=0.05, interval=0) == pytest.approx(7.29)


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


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

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
