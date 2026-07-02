"""Tests for the Gantry SiLA feature - the glue between GantryControllerProtocol and the wire.

No pytest-asyncio dependency is used (the project has none); coroutines are
driven directly with asyncio.run(), matching how a real event loop would call
them one step at a time. Mirrors devices/ph_sensor/backend/tests/test_feature.py.
"""
import asyncio

import pytest

from rxn_bench_gantry.errors import MotionLimitError
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

    def get_position(self) -> dict[str, float]:
        return {"x": 0.0, "y": 0.0, "z": 0.0}

    def get_state(self) -> str:
        return "idle"

    def move_to(self, x=None, y=None, z=None, speed=None) -> None:
        self.move_to_calls.append((x, y, z, speed))
        if self.raise_on_move_to:
            raise self.raise_on_move_to

    def move_to_well(self, label: str, override_unvalidated: bool = False) -> None:
        self.move_to_well_calls.append((label, override_unvalidated))
        if self.raise_on_move_to:
            raise self.raise_on_move_to

    def list_toolheads(self) -> list[tuple[str, str]]:
        return self.toolheads

    def list_workspaces(self) -> list[str]:
        return self.workspaces


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
    with pytest.raises(RuntimeError, match="already running"):
        asyncio.run(feature.acquire_experiment_lock())


def test_release_experiment_lock_returns_to_idle():
    feature = Gantry(controller=_FakeController())
    asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.release_experiment_lock())
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


def test_motion_is_not_rejected_while_experiment_lock_is_held():
    """Characterizes a known gap (see docs/ai/CURRENT_STATE.md #6): _run() only
    serializes on _hw_lock and never checks _experiment_state, so a motion RPC
    sent while a script holds the experiment lock is executed, not rejected.
    This test pins that behavior; it should start failing the moment the gap
    is fixed, which is the signal to update/remove this test.
    """
    ctrl = _FakeController()
    feature = Gantry(controller=ctrl)
    asyncio.run(feature.acquire_experiment_lock())
    asyncio.run(feature.move_to(1.0, 2.0, 3.0))
    assert ctrl.move_to_calls == [(1.0, 2.0, 3.0, None)]
