"""Smoke tests for GantryController using MockMoonrakerClient."""
import pytest

from chem_bench_gantry.controller import GantryController
from chem_bench_gantry.mock_moonraker import MockMoonrakerClient
from chem_bench_gantry.errors import MotionLimitError


@pytest.fixture
def ctrl():
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
    x_min, x_max, y_min, y_max, z_min, z_max = [float(p) for p in parts]
    assert x_min == 0.0
    assert x_max == 300.0
    assert y_min == 0.0
    assert y_max == 300.0
    assert z_min == 0.0
    assert z_max == 250.0


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


def test_jog_smoke(ctrl):
    ctrl.move_to(150.0, 150.0, 50.0)
    ctrl.jog(dx=10.0)


def test_save_requires_calibration(ctrl, tmp_path, monkeypatch):
    import chem_bench_gantry.homing_state as hs
    monkeypatch.setattr(hs, "_STATE_FILE", tmp_path / "homing_state.json")
    with pytest.raises(RuntimeError, match="not been calibrated"):
        ctrl.save_and_park()


def test_save_allowed_after_homing(ctrl, tmp_path, monkeypatch):
    import chem_bench_gantry.homing_state as hs
    monkeypatch.setattr(hs, "_STATE_FILE", tmp_path / "homing_state.json")
    ctrl.home_auto()
    ctrl.save_and_park()
    assert (tmp_path / "homing_state.json").exists()
