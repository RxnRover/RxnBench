"""Tests for the Gantry instrument wrapper.

A fake SiLA client stands in for the live server: it records every command
call (name + kwargs) so tests can assert the lock token is attached, and
serves canned labware/workspace responses for the well-enumeration logic.
"""
import textwrap

import pytest

from rxn_bench_client.instruments.motion import Gantry, _well_labels

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


def test_shake_default_alternates_axes(gantry, feature):
    gantry.shake(amplitude=1.0, cycles=4)  # default axis="xy": round-robin x, y, x, y
    jogs = [kw for name, kw in feature.calls if name == "Jog"]
    assert len(jogs) == 8  # two half-strokes per cycle
    axes_hit = [(j["Dx"], j["Dy"], j["Dz"]) for j in jogs[::2]]  # one per cycle (the "out" jog)
    assert axes_hit == [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]


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


# Auto-snapshot: a few methods ask the owning bench for a picture

class _FakeBench:
    def __init__(self):
        self.snapshots: list[str] = []

    def snapshot(self, label):
        self.snapshots.append(label)


@pytest.mark.parametrize(
    "call, label",
    [
        (lambda g: g.move_to_well("plate1/A1"), "move_to_well"),
        (lambda g: g.engage_tool(depth=5.0), "engage_tool"),
        (lambda g: g.disengage_tool(depth=5.0), "disengage_tool"),
    ],
)
def test_action_methods_auto_snapshot_when_attached_to_a_bench(gantry, call, label):
    gantry._bench = _FakeBench()
    call(gantry)
    assert gantry._bench.snapshots == [label]


@pytest.mark.parametrize(
    "call",
    [
        lambda g: g.move_to(1.0, 2.0, 3.0),
        lambda g: g.jog(dx=1.0),
        lambda g: g.shake(cycles=1),
    ],
)
def test_low_level_motion_methods_do_not_auto_snapshot(gantry, call):
    """move_to/jog/shake are frequent, low-level primitives (shake() alone
    fires dozens of jogs) - snapshotting them would flood the log."""
    gantry._bench = _FakeBench()
    call(gantry)
    assert gantry._bench.snapshots == []


def test_action_methods_do_not_snapshot_without_a_bench(gantry):
    """A Gantry constructed directly (not via bench.connect()/_attach()) has
    no _bench attribute at all - must not raise."""
    gantry.move_to_well("plate1/A1")
    gantry.engage_tool(depth=5.0)
