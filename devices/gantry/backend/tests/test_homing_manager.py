"""Tests for HomingManager's manual/auto homing state machine and limit persistence."""
import pytest

import rxn_bench_gantry.homing_state as homing_state
from rxn_bench_gantry.errors import MotionLimitError
from rxn_bench_gantry.homing_manager import _HOMING_SAFE_MID, HomingManager

from tests.fakes import FakeMotionClient


@pytest.fixture
def client():
    return FakeMotionClient()


@pytest.fixture
def mgr(client):
    return HomingManager(
        client,
        clearance_z=50.0,
        x_min=0.0, x_max=300.0,
        y_min=0.0, y_max=300.0,
        z_min=0.0, z_max=250.0,
    )


def test_home_auto_skips_z_raise_when_z_not_yet_homed(mgr, client):
    mgr.home_auto(safe_clearance_z=75.0)
    assert ("move", {"x": None, "y": None, "z": 75.0, "speed": None}) not in client.calls
    assert ("home", {"axes": "XY"}) in client.calls


def test_home_auto_raises_to_clearance_first_when_z_already_homed(mgr, client):
    client._homed_axes = "xyz"
    mgr.home_auto(safe_clearance_z=75.0)
    names = [name for name, _ in client.calls]
    assert names[0] == "move"
    assert client.calls[0][1]["z"] == 75.0
    assert names[1] == "home"


def test_home_auto_sets_safe_kinematic_z_midpoint(mgr, client):
    mgr.home_auto(safe_clearance_z=75.0)
    assert ("set_kinematic_position", {"x": None, "y": None, "z": _HOMING_SAFE_MID}) in client.calls


def test_home_auto_marks_machine_calibrated(mgr):
    mgr.home_auto(safe_clearance_z=75.0)
    mgr.save(toolhead_name="")  # does not raise once calibrated


def test_start_manual_homing_centers_carriage_and_resets_accumulators(mgr, client):
    mgr.start_manual_homing()
    assert mgr.homing_active
    assert client.calls[-1] == (
        "set_kinematic_position",
        {"x": _HOMING_SAFE_MID, "y": _HOMING_SAFE_MID, "z": _HOMING_SAFE_MID},
    )


def test_start_manual_homing_invalidates_saved_state(mgr, client):
    mgr.home_auto(safe_clearance_z=75.0)
    mgr.save(toolhead_name="ph_probe")
    assert mgr.has_saved_state

    mgr.start_manual_homing()
    assert not mgr.has_saved_state
    assert homing_state.load() is None


def test_confirm_x_min_zeroes_x_min_and_resets_accumulator(mgr, client):
    mgr.start_manual_homing()
    mgr.homing_jog_update(dx=20.0, dy=0.0, dz=0.0)
    mgr.confirm_x_min()
    assert mgr.x_min == 0.0
    with pytest.raises(MotionLimitError):
        mgr.confirm_x_max()  # accumulator was reset by confirm_x_min


def test_confirm_x_max_requires_at_least_1mm_of_travel(mgr):
    mgr.start_manual_homing()
    with pytest.raises(MotionLimitError, match="at least 1 mm"):
        mgr.confirm_x_max()


def test_confirm_x_max_records_accumulated_travel(mgr):
    mgr.start_manual_homing()
    mgr.homing_jog_update(dx=120.0, dy=0.0, dz=0.0)
    mgr.confirm_x_max()
    assert mgr.x_max == 120.0


def test_confirm_y_min_zeroes_y_min(mgr, client):
    mgr.start_manual_homing()
    mgr.confirm_y_min()
    assert mgr.y_min == 0.0


def test_confirm_y_max_requires_at_least_1mm_of_travel(mgr):
    mgr.start_manual_homing()
    with pytest.raises(MotionLimitError, match="at least 1 mm"):
        mgr.confirm_y_max()


def test_confirm_y_max_records_accumulated_travel(mgr):
    mgr.start_manual_homing()
    mgr.homing_jog_update(dx=0.0, dy=88.0, dz=0.0)
    mgr.confirm_y_max()
    assert mgr.y_max == 88.0


def test_confirm_z_reference_zeroes_kinematic_z(mgr, client):
    mgr.start_manual_homing()
    mgr.confirm_z_reference()
    assert ("set_kinematic_position", {"x": None, "y": None, "z": 0}) in client.calls


def test_homing_jog_update_recenters_kinematic_position_per_call(mgr, client):
    mgr.start_manual_homing()
    mgr.homing_jog_update(dx=10.0, dy=0.0, dz=0.0)
    assert client.calls[-1] == (
        "set_kinematic_position", {"x": _HOMING_SAFE_MID - 10.0, "y": None, "z": None},
    )

    mgr.homing_jog_update(dx=15.0, dy=0.0, dz=0.0)
    assert client.calls[-1] == (
        "set_kinematic_position", {"x": _HOMING_SAFE_MID - 15.0, "y": None, "z": None},
    )
    # Accumulator sums across calls even though the kinematic reset does not.
    mgr.confirm_x_max()
    assert mgr.x_max == 25.0


def test_finish_homing_ends_homing_and_marks_calibrated(mgr):
    mgr.start_manual_homing()
    mgr.finish_homing()
    assert not mgr.homing_active
    mgr.save(toolhead_name="")  # does not raise once calibrated


def test_save_requires_calibration_this_session(mgr):
    with pytest.raises(RuntimeError, match="not been calibrated"):
        mgr.save(toolhead_name="")


def test_save_persists_limits_and_toolhead_name(mgr):
    mgr.home_auto(safe_clearance_z=75.0)
    mgr.confirm_x_min()
    mgr.save(toolhead_name="ph_probe")

    assert mgr.has_saved_state
    saved = homing_state.load()
    assert saved is not None
    assert saved["toolhead_name"] == "ph_probe"
    assert saved["x_min"] == mgr.x_min
    assert saved["x_max"] == mgr.x_max


def test_restore_loads_persisted_limits_and_returns_toolhead_name(client):
    mgr1 = HomingManager(client, x_min=0.0, x_max=300.0, y_min=0.0, y_max=300.0)
    mgr1.home_auto(safe_clearance_z=75.0)
    mgr1.confirm_x_min()
    mgr1.save(toolhead_name="ph_probe")

    mgr2 = HomingManager(FakeMotionClient(), x_min=0.0, x_max=999.0, y_min=0.0, y_max=999.0)
    toolhead_name = mgr2.restore()
    assert toolhead_name == "ph_probe"
    assert mgr2.x_max == mgr1.x_max
    assert mgr2.has_saved_state
    with pytest.raises(RuntimeError, match="not been calibrated"):
        mgr2.save(toolhead_name="ph_probe")  # restore() does not imply calibrated-this-session


def test_invalidate_state_prevents_restore_and_save(mgr):
    mgr.home_auto(safe_clearance_z=75.0)
    mgr.save(toolhead_name="ph_probe")

    mgr.invalidate_state()
    assert not mgr.has_saved_state
    assert homing_state.load() is None
    with pytest.raises(RuntimeError, match="not been calibrated"):
        mgr.save(toolhead_name="ph_probe")
