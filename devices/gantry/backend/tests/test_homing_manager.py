"""Tests for HomingManager's manual/auto homing state machine and limit persistence."""
import pytest

import rxn_bench_gantry.homing_state as homing_state
from rxn_bench_gantry.homing_manager import _HOMING_SAFE_MID, HomingManager

from tests.fakes import FakeMotionClient


@pytest.fixture
def client():
    return FakeMotionClient()


@pytest.fixture
def mgr(client):
    return HomingManager(
        client,
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


def test_start_manual_homing_centers_carriage(mgr, client):
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


def test_confirm_x_min_zeroes_x_min_and_the_real_position(mgr, client):
    mgr.start_manual_homing()
    client.jog(dx=20.0)  # real move, e.g. via controller.jog() during homing
    mgr.confirm_x_min()
    assert mgr.x_min == 0.0
    assert client.get_position()["x"] == 0.0


def test_confirm_x_min_does_not_touch_x_max(mgr):
    # x_max is a fixed machine constant now - only the origin is re-established.
    mgr.start_manual_homing()
    mgr.confirm_x_min()
    assert mgr.x_max == 300.0


def test_confirm_y_min_zeroes_y_min_and_the_real_position(mgr, client):
    mgr.start_manual_homing()
    mgr.confirm_y_min()
    assert mgr.y_min == 0.0
    assert client.get_position()["y"] == 0.0


def test_confirm_y_min_does_not_touch_y_max(mgr):
    mgr.start_manual_homing()
    mgr.confirm_y_min()
    assert mgr.y_max == 300.0


def test_confirm_x_max_declares_x_max_without_touching_x_min(mgr, client):
    # Operator's choice per session - pick whichever X corner is convenient.
    mgr.start_manual_homing()
    mgr.confirm_x_max()
    assert ("set_kinematic_position", {"x": 300.0, "y": None, "z": None}) in client.calls
    assert mgr.x_min == 0.0  # the fixed bed-width constant is untouched
    assert mgr.x_max == 300.0


def test_confirm_y_max_declares_y_max_without_touching_y_min(mgr, client):
    mgr.start_manual_homing()
    mgr.confirm_y_max()
    assert ("set_kinematic_position", {"x": None, "y": 300.0, "z": None}) in client.calls
    assert mgr.y_min == 0.0
    assert mgr.y_max == 300.0


def test_confirm_z_reference_zeroes_kinematic_z(mgr, client):
    mgr.start_manual_homing()
    mgr.confirm_z_reference()
    assert ("set_kinematic_position", {"x": None, "y": None, "z": 0}) in client.calls


def test_jogging_during_manual_homing_is_a_single_real_move(mgr, client):
    """No shadow accumulator, no per-jog kinematic relabeling - just the real move."""
    mgr.start_manual_homing()
    calls_before = len(client.calls)
    client.jog(dx=10.0)
    assert len(client.calls) == calls_before + 1
    assert client.calls[-1] == ("jog", {"dx": 10.0, "dy": 0.0, "dz": 0.0, "speed": None})
    assert client.get_position()["x"] == pytest.approx(_HOMING_SAFE_MID + 10.0)


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
