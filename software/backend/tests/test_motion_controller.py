"""
Smoke tests for GantryController using MockMoonrakerClient.

Exercises: move_to, jog, bounds checking, homing state guard, and get_limits.
No hardware required — activated via the in-memory mock client.
"""
import pytest

from chem_bench.io.gantry.gantry_controller import GantryController
from chem_bench.io.gantry.mock_moonraker import MockMoonrakerClient
from chem_bench.io.errors import MotionLimitError


@pytest.fixture
def ctrl():
    """Controller wired to MockMoonrakerClient with known limits."""
    client = MockMoonrakerClient()
    return GantryController(
        client=client,
        clearance_z=50.0,
        x_min=0.0, x_max=300.0,
        y_min=0.0, y_max=300.0,
        z_min=0.0, z_max=250.0,
    )


def test_get_limits_format(ctrl):
    limits_str = ctrl.get_limits()
    parts = limits_str.split("|")
    assert len(parts) == 6
    floats = [float(p) for p in parts]
    x_min, x_max, y_min, y_max, z_min, z_max = floats
    assert x_min == 0.0
    assert x_max == 300.0
    assert y_min == 0.0
    assert y_max == 300.0
    assert z_min == 0.0
    assert z_max == 250.0


def test_move_to_within_bounds(ctrl):
    # Should not raise
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


def test_jog_smoke(ctrl):
    # Jog with no active toolhead and no homing — should not raise for valid deltas
    ctrl.move_to(150.0, 150.0, 50.0)
    ctrl.jog(dx=10.0)


def test_save_requires_calibration(ctrl, tmp_path, monkeypatch):
    """save_and_park must raise if no fresh homing has been performed."""
    import chem_bench.io.gantry.homing_state as hs
    monkeypatch.setattr(hs, "_STATE_FILE", tmp_path / "homing_state.json")
    with pytest.raises(RuntimeError, match="not been calibrated"):
        ctrl.save_and_park()


def test_save_allowed_after_homing(ctrl, tmp_path, monkeypatch):
    """save_and_park succeeds after home_auto marks limits as calibrated."""
    import chem_bench.io.gantry.homing_state as hs
    monkeypatch.setattr(hs, "_STATE_FILE", tmp_path / "homing_state.json")
    # home_auto sets _is_calibrated = True on HomingManager
    ctrl.home_auto()
    # Now save_and_park should succeed (parks first, then saves)
    ctrl.save_and_park()
    assert (tmp_path / "homing_state.json").exists()
