"""Tests for GantryController: bounds enforcement, toolhead-aware limits, homing integration."""
import pytest

from rxn_bench_gantry.controller import GantryController
from rxn_bench_gantry.errors import MotionLimitError

from tests.fakes import FakeMotionClient


@pytest.fixture
def client():
    return FakeMotionClient()


@pytest.fixture
def ctrl(client):
    return GantryController(
        client=client,
        clearance_z=50.0,
        x_min=0.0, x_max=300.0,
        y_min=0.0, y_max=300.0,
        z_min=0.0, z_max=250.0,
    )


# ---------------------------------------------------------------------------
# Bare-carriage bounds (no toolhead mounted)
# ---------------------------------------------------------------------------

def test_get_limits_format(ctrl):
    limits_str = ctrl.get_limits()
    parts = limits_str.split("|")
    assert len(parts) == 6
    x_min, x_max, y_min, y_max, z_min, z_max = [float(p) for p in parts]
    assert (x_min, x_max, y_min, y_max, z_min, z_max) == (0.0, 300.0, 0.0, 300.0, 0.0, 250.0)


def test_move_to_within_bounds(ctrl):
    ctrl.move_to(100.0, 100.0, 50.0)


def test_move_to_exceeds_x(ctrl):
    with pytest.raises(MotionLimitError):
        ctrl.move_to(350.0, 100.0, 50.0)


def test_move_to_exceeds_y(ctrl):
    with pytest.raises(MotionLimitError):
        ctrl.move_to(100.0, 350.0, 50.0)


def test_move_to_exceeds_z(ctrl):
    with pytest.raises(MotionLimitError):
        ctrl.move_to(100.0, 100.0, 300.0)


def test_move_to_issues_clearance_sequence_to_client(ctrl, client):
    ctrl.move_to(100.0, 100.0, 50.0)
    assert [name for name, _ in client.calls] == ["move", "move", "move"]
    assert client.calls[0][1]["z"] == 50.0  # ctrl's clearance_z, no toolhead mounted
    assert client.calls[1][1] == {"x": 100.0, "y": 100.0, "z": None, "speed": None}
    assert client.calls[2][1]["z"] == 50.0


def test_jog_within_bounds_delegates_to_client(ctrl, client):
    ctrl.move_to(150.0, 150.0, 50.0)
    client.calls.clear()
    ctrl.jog(dx=10.0)
    assert client.calls == [("jog", {"dx": 10.0, "dy": 0.0, "dz": 0.0, "speed": None})]


def test_jog_exceeding_bounds_raises_before_touching_client(ctrl, client):
    ctrl.move_to(295.0, 100.0, 50.0)
    client.calls.clear()
    with pytest.raises(MotionLimitError):
        ctrl.jog(dx=10.0)
    assert client.calls == []


def test_engage_tool_lowers_z_by_depth(ctrl, client):
    client._z = 50.0  # start somewhere engage_tool's descent won't violate z_min
    ctrl.engage_tool(depth=5.0)
    assert client.calls == [("move", {"x": None, "y": None, "z": 45.0, "speed": None})]


def test_disengage_tool_raises_z_by_depth(ctrl, client):
    ctrl.disengage_tool(depth=5.0)
    assert client.calls == [("move", {"x": None, "y": None, "z": 5.0, "speed": None})]


def test_disengage_tool_exceeding_z_max_raises(ctrl):
    with pytest.raises(MotionLimitError):
        ctrl.disengage_tool(depth=300.0)


# ---------------------------------------------------------------------------
# Toolhead-aware bounds (footprint + tip offset compensation)
# ---------------------------------------------------------------------------

def test_toolhead_footprint_narrows_x_bounds(ctrl):
    ctrl.set_toolhead("ph_probe")  # footprint_x=44 -> half-width 22mm
    with pytest.raises(MotionLimitError):
        ctrl.move_to(290.0, 100.0, 150.0)  # 290 + 22 = 312 > x_max=300


def test_bare_carriage_allows_same_position_toolhead_would_reject(ctrl):
    # No toolhead mounted -> zero footprint -> 290 alone is within [0, 300].
    ctrl.move_to(290.0, 100.0, 150.0)


def test_toolhead_offset_shifts_physical_target(ctrl, client):
    ctrl.set_toolhead("ph_probe")  # offset_x=0, offset_y=-35, tip_x=0, tip_y=-25
    ctrl.move_to(100.0, 150.0, 150.0)
    xy_args = client.calls[1][1]
    assert xy_args["x"] == pytest.approx(100.0)  # offset_x + tip_x == 0
    assert xy_args["y"] == pytest.approx(90.0)  # 150 + (offset_y + tip_y) == 150 - 60


def test_toolhead_tip_offset_z_raises_safe_clearance_height(ctrl, client):
    ctrl.set_toolhead("ph_probe")  # tip_offset_z=110mm, deeper than the default clearance_z=50mm
    ctrl.move_to(100.0, 150.0, 150.0)
    assert client.calls[0][1]["z"] == 110.0  # max(clearance_z=50, tip_offset_z=110)


def test_toolhead_tip_below_z_min_raises(ctrl):
    ctrl.set_toolhead("ph_probe")  # tip_offset_z=110mm below the carriage
    with pytest.raises(MotionLimitError, match="tool tip"):
        ctrl.move_to(100.0, 150.0, 50.0)  # tip would sit at 50 - 110 = -60mm, below z_min=0


def test_clear_toolhead_restores_bare_carriage_bounds(ctrl):
    ctrl.set_toolhead("ph_probe")
    ctrl.clear_toolhead()
    ctrl.move_to(290.0, 100.0, 150.0)  # no longer rejected once footprint is gone


def test_set_toolhead_invalidates_saved_homing_state(ctrl):
    ctrl.home_auto()
    ctrl.save_and_park()
    assert ctrl.has_saved_state

    ctrl.set_toolhead("ph_probe")
    assert not ctrl.has_saved_state


# ---------------------------------------------------------------------------
# Homing / saved-state integration
# ---------------------------------------------------------------------------

def test_save_requires_calibration(ctrl):
    with pytest.raises(RuntimeError, match="not been calibrated"):
        ctrl.save_and_park()


def test_save_allowed_after_homing(ctrl):
    ctrl.home_auto()
    ctrl.save_and_park()
    assert ctrl.has_saved_state
