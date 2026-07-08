"""Tests for the Gantry SiLA feature - the glue between GantryControllerProtocol and the wire.

No pytest-asyncio dependency is used (the project has none); coroutines are
driven directly with asyncio.run(), matching how a real event loop would call
them one step at a time. Mirrors devices/ph_sensor/backend/tests/test_feature.py.
"""
import asyncio

import pytest

from rxn_bench_gantry.errors import ExperimentLockError, MotionLimitError
from rxn_bench_gantry.feature import Gantry


class _FakeController:
    def __init__(self):
        self.has_saved_state = False
        self.toolhead_mounted = False
        self.move_to_calls: list[tuple] = []
        self.move_to_well_calls: list[tuple] = []
        self.raise_on_move_to: Exception | None = None
        self.toolheads = [("ph_probe", "Atlas Scientific pH Probe")]
        self.workspaces = ["plate_96well"]
        self.workspace_yaml = ""
        self.labware_yaml = "96_well_standard:\n  rows: 8\n"
        self.mounted_toolheads: list[str] = []
        self.toolhead = None  # set to a stub with the ToolheadGeometry-shaped fields to test the "active" branch

    def get_position(self) -> dict[str, float]:
        return {"x": 0.0, "y": 0.0, "z": 0.0}

    def get_state(self) -> str:
        return "idle"

    def move_to(self, x=None, y=None, z=None, speed=None) -> None:
        self.move_to_calls.append((x, y, z, speed))
        if self.raise_on_move_to:
            raise self.raise_on_move_to

    def move_to_well(self, label: str, override_unvalidated: bool = False) -> dict[str, float]:
        self.move_to_well_calls.append((label, override_unvalidated))
        if self.raise_on_move_to:
            raise self.raise_on_move_to
        return {
            "expected_well_x": 1.0, "expected_well_y": 2.0,
            "actual_x": 1.5, "actual_y": 2.5,
        }

    def jog(self, dx=0.0, dy=0.0, dz=0.0, speed=None) -> None:
        pass

    def list_toolheads(self) -> list[tuple[str, str]]:
        return self.toolheads

    def get_toolhead(self):
        return self.toolhead

    def get_toolhead_name(self) -> str:
        return self.toolhead.name if self.toolhead else ""

    def get_toolhead_display_name(self) -> str:
        return self.toolhead.display_name if self.toolhead else ""

    def get_mounted_toolheads(self) -> list[str]:
        return self.mounted_toolheads

    def list_workspaces(self) -> list[str]:
        return self.workspaces

    def set_workspace(self, name: str) -> None:
        self.workspace_yaml = f"name: {name}\nplates: []\n"

    def load_workspace_from_yaml(self, content: str) -> None:
        self.workspace_yaml = content

    def get_workspace_yaml(self) -> str:
        return self.workspace_yaml

    def get_labware_yaml(self) -> str:
        return self.labware_yaml


async def _first(agen):
    try:
        return await agen.__anext__()
    finally:
        await agen.aclose()


# ---------------------------------------------------------------------------
# Motion commands - current_action bookkeeping
# ---------------------------------------------------------------------------

def test_move_to_forwards_to_controller():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.move_to(1.0, 2.0, 3.0))
    assert ctrl.move_to_calls == [(1.0, 2.0, 3.0, None)]


def test_move_to_sets_current_action_to_standby_on_success():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.move_to(1.0, 2.0, 3.0))
    assert asyncio.run(_first(feature.current_action())) == "Standby"


def test_move_to_records_error_in_current_action_and_reraises():
    ctrl = _FakeController()
    ctrl.raise_on_move_to = MotionLimitError("X exceeds limits")
    feature = Gantry(controller=ctrl)
    with pytest.raises(MotionLimitError):
        asyncio.run(feature.move_to(999.0, 2.0, 3.0))
    assert "X exceeds limits" in asyncio.run(_first(feature.current_action()))


def test_move_to_well_records_current_well_on_success():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.move_to_well("plate1/A3"))
    assert asyncio.run(_first(feature.current_well())) == "plate1/A3"


def test_move_to_well_does_not_record_current_well_on_failure():
    ctrl = _FakeController()
    ctrl.raise_on_move_to = MotionLimitError("out of bounds")
    feature = Gantry(controller=ctrl)
    with pytest.raises(MotionLimitError):
        asyncio.run(feature.move_to_well("plate1/A3"))


def test_move_to_well_forwards_override_unvalidated_flag():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.move_to_well("plate1/A3", override_unvalidated=True))
    assert ctrl.move_to_well_calls == [("plate1/A3", True)]


def test_move_to_well_defaults_override_unvalidated_to_false():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.move_to_well("plate1/A3"))
    assert ctrl.move_to_well_calls == [("plate1/A3", False)]


def test_move_to_well_logs_expected_and_actual_position():
    """_run() merges a dict return value into the log entry.

    Lets every well move's session log line show the well's expected nominal
    position alongside the gantry's actual position, so a hand-computed
    geometry mismatch is visible without needing the calibration wizard.
    """
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    logged = []
    feature._log.log = lambda event, **kw: logged.append((event, kw))
    asyncio.run(feature.move_to_well("plate1/A3"))
    assert logged == [(
        "move_to_well",
        {
            "ok": True, "well": "plate1/A3",
            "expected_well_x": 1.0, "expected_well_y": 2.0,
            "actual_x": 1.5, "actual_y": 2.5,
        },
    )]


# ---------------------------------------------------------------------------
# Toolhead / workspace listing glue
# ---------------------------------------------------------------------------

def test_list_toolheads_formats_name_pipe_display_name():
    feature = Gantry(controller=_FakeController())
    assert asyncio.run(feature.list_toolheads()) == "ph_probe|Atlas Scientific pH Probe"


def test_list_workspaces_returns_newline_delimited_names():
    ctrl = _FakeController()
    ctrl.workspaces = ["plate_96well", "plate_24well"]
    feature = Gantry(controller=ctrl)
    assert asyncio.run(feature.list_workspaces()) == "plate_96well\nplate_24well"


# ---------------------------------------------------------------------------
# Experiment lock state machine
# ---------------------------------------------------------------------------

def test_experiment_starts_idle():
    feature = Gantry(controller=_FakeController())
    assert asyncio.run(feature.get_experiment_state()) == "idle"
    assert asyncio.run(_first(feature.experiment_active())) is False


def test_acquire_experiment_lock_moves_idle_to_running():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    assert asyncio.run(feature.get_experiment_state()) == "running"
    assert asyncio.run(_first(feature.experiment_active())) is True


def test_acquire_experiment_lock_rejects_when_already_running():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    with pytest.raises(ExperimentLockError, match="already running"):
        asyncio.run(feature.acquire_experiment_lock())


def test_acquire_experiment_lock_returns_a_token():
    feature = Gantry(controller=_FakeController())
    token = asyncio.run(feature.acquire_experiment_lock())
    assert isinstance(token, str) and len(token) >= 16


def test_release_experiment_lock_returns_to_idle():
    feature = Gantry(controller=_FakeController())
    token = asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.release_experiment_lock(token))
    assert asyncio.run(feature.get_experiment_state()) == "idle"


def test_release_experiment_lock_rejects_wrong_token():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    with pytest.raises(ExperimentLockError):
        asyncio.run(feature.release_experiment_lock("not-the-token"))
    assert asyncio.run(feature.get_experiment_state()) == "running"


def test_release_experiment_lock_is_noop_while_idle():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.release_experiment_lock("anything"))
    assert asyncio.run(feature.get_experiment_state()) == "idle"


def test_pause_experiment_only_transitions_from_running():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.pause_experiment())  # no-op while idle
    assert asyncio.run(feature.get_experiment_state()) == "idle"

    asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.pause_experiment())
    assert asyncio.run(feature.get_experiment_state()) == "paused"


def test_resume_experiment_only_transitions_from_paused():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.resume_experiment())  # no-op while running, not paused
    assert asyncio.run(feature.get_experiment_state()) == "running"

    asyncio.run(feature.pause_experiment())
    asyncio.run(feature.resume_experiment())
    assert asyncio.run(feature.get_experiment_state()) == "running"


def test_stop_experiment_from_running_or_paused():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.stop_experiment())
    assert asyncio.run(feature.get_experiment_state()) == "stop_requested"


def test_stop_experiment_is_noop_while_idle():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.stop_experiment())
    assert asyncio.run(feature.get_experiment_state()) == "idle"


# ---------------------------------------------------------------------------
# Experiment lock gating of motion / toolhead / workspace commands
# ---------------------------------------------------------------------------

def test_motion_without_token_is_rejected_while_lock_is_held():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.acquire_experiment_lock())
    with pytest.raises(ExperimentLockError):
        asyncio.run(feature.move_to(1.0, 2.0, 3.0))
    assert ctrl.move_to_calls == []


def test_motion_with_lock_token_is_accepted_while_lock_is_held():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    token = asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.move_to(1.0, 2.0, 3.0, token=token))
    asyncio.run(feature.move_to_well("plate1/A3", token=token))
    assert ctrl.move_to_calls == [(1.0, 2.0, 3.0, None)]
    assert ctrl.move_to_well_calls == [("plate1/A3", False)]


def test_motion_without_token_works_while_idle():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.jog(dx=1.0))
    asyncio.run(feature.move_to(1.0, 2.0, 3.0))
    assert ctrl.move_to_calls == [(1.0, 2.0, 3.0, None)]


def test_homing_is_always_rejected_while_lock_is_held():
    """Homing commands accept no token: scripts never calibrate limits mid-run."""
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    with pytest.raises(ExperimentLockError):
        asyncio.run(feature.start_manual_homing())
    with pytest.raises(ExperimentLockError):
        asyncio.run(feature.confirm_x_min())


def test_gating_lifts_after_release():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    token = asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.release_experiment_lock(token))
    asyncio.run(feature.move_to(1.0, 2.0, 3.0))
    assert ctrl.move_to_calls == [(1.0, 2.0, 3.0, None)]


def test_pause_and_stop_remain_available_without_token():
    """The UI must always be able to pause/stop a running experiment."""
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.pause_experiment())
    assert asyncio.run(feature.get_experiment_state()) == "paused"
    asyncio.run(feature.stop_experiment())
    assert asyncio.run(feature.get_experiment_state()) == "stop_requested"


def test_force_release_recovers_a_stranded_lock():
    """A killed script takes its token to the grave; force-release is the
    tokenless recovery so the bench doesn't need a server restart."""
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.stop_experiment())          # the state the user got stuck in
    asyncio.run(feature.force_release_experiment_lock())
    assert asyncio.run(feature.get_experiment_state()) == "idle"
    # Bench is fully usable again: manual motion and a fresh lock both work.
    asyncio.run(feature.move_to(1.0, 2.0, 3.0))
    token = asyncio.run(feature.acquire_experiment_lock())
    assert token


def test_force_release_is_noop_while_idle():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.force_release_experiment_lock())
    assert asyncio.run(feature.get_experiment_state()) == "idle"


# ---------------------------------------------------------------------------
# Workspace YAML source of truth + labware
# ---------------------------------------------------------------------------

def test_get_workspace_yaml_reflects_set_workspace_by_name():
    """Loading a workspace by name must be visible via GetWorkspaceYaml (this
    was previously cached at the feature level and only updated by
    LoadWorkspaceYaml, leaving name-loaded workspaces invisible to clients)."""
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.set_workspace("bench_default"))
    assert "bench_default" in asyncio.run(feature.get_workspace_yaml())


def test_current_workspace_yaml_stream_reflects_controller_state():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    assert asyncio.run(_first(feature.current_workspace_yaml())) == ""
    asyncio.run(feature.load_workspace_yaml("name: from_yaml\nplates: []\n"))
    assert "from_yaml" in asyncio.run(_first(feature.current_workspace_yaml()))


def test_get_labware_returns_controller_yaml():
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    assert asyncio.run(feature.get_labware()) == ctrl.labware_yaml


def test_toolhead_info_streams_per_head_mount_state():
    """The stream carries every confirmed head (pipe-delimited), so the UI can
    show both slots' mount readiness, not just the active head's."""
    ctrl = _FakeController()
    ctrl.mounted_toolheads = ["ph_probe", "pipette"]
    feature = Gantry(controller=ctrl)
    info = asyncio.run(_first(feature.toolhead_info()))
    assert info.mounted_toolheads == "ph_probe|pipette"


class _FakeToolheadGeometry:
    """Minimal ToolheadGeometry-shaped stub for exercising toolhead_info's active branch."""

    def __init__(self, calibrated_at: str = ""):
        self.name = "ph_probe"
        self.display_name = "Atlas Scientific pH Probe"
        self.footprint_x = 44.0
        self.footprint_y = 25.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.tip_offset_z = 0.0
        self.z_engage = 25.0
        self.tip_x = 1.0
        self.tip_y = 2.0
        self.calibrated_at = calibrated_at


def test_toolhead_info_streams_calibrated_at_for_active_head():
    """Without this field, the UI has no way to show when a toolhead was last
    calibrated - it's blank in the config and only known via the persisted
    calibration state the controller applies onto the active toolhead."""
    ctrl = _FakeController()
    ctrl.toolhead = _FakeToolheadGeometry(calibrated_at="2026-07-08T17:06:54")
    feature = Gantry(controller=ctrl)
    info = asyncio.run(_first(feature.toolhead_info()))
    assert info.active is True
    assert info.calibrated_at == "2026-07-08T17:06:54"


def test_toolhead_info_calibrated_at_blank_when_never_calibrated():
    ctrl = _FakeController()
    ctrl.toolhead = _FakeToolheadGeometry(calibrated_at="")
    feature = Gantry(controller=ctrl)
    info = asyncio.run(_first(feature.toolhead_info()))
    assert info.calibrated_at == ""


def test_toolhead_info_calibrated_at_blank_when_no_active_toolhead():
    ctrl = _FakeController()  # ctrl.toolhead stays None
    feature = Gantry(controller=ctrl)
    info = asyncio.run(_first(feature.toolhead_info()))
    assert info.active is False
    assert info.calibrated_at == ""
