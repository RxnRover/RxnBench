"""Tests for the in-memory Moonraker simulator used in RXN_BENCH_MOCK=1 mode."""
import pytest

import rxn_bench_gantry.mock_moonraker as mock_moonraker
from rxn_bench_gantry.interfaces import MotionClientProtocol
from rxn_bench_gantry.mock_moonraker import MockMoonrakerClient


@pytest.fixture(autouse=True)
def _no_simulated_delay(monkeypatch):
    monkeypatch.setattr(mock_moonraker.time, "sleep", lambda _seconds: None)


def test_satisfies_protocol():
    assert isinstance(MockMoonrakerClient(), MotionClientProtocol)


def test_starts_at_origin_unhomed():
    client = MockMoonrakerClient()
    assert client.get_position() == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert client.get_homed_axes() == ""


def test_move_updates_position_and_returns_to_ready():
    client = MockMoonrakerClient()
    client.move(x=10.0, y=20.0, z=5.0)
    assert client.get_position() == {"x": 10.0, "y": 20.0, "z": 5.0}
    assert client.get_state() == "ready"


def test_move_skips_axes_left_as_none():
    client = MockMoonrakerClient()
    client.move(x=10.0, y=20.0, z=5.0)
    client.move(z=50.0)
    assert client.get_position() == {"x": 10.0, "y": 20.0, "z": 50.0}


def test_jog_moves_relative_to_current_position():
    client = MockMoonrakerClient()
    client.move(x=10.0, y=10.0, z=10.0)
    client.jog(dx=5.0, dy=-2.0, dz=0.0)
    assert client.get_position() == {"x": 15.0, "y": 8.0, "z": 10.0}


def test_home_resets_only_specified_axes():
    client = MockMoonrakerClient()
    client.move(x=10.0, y=10.0, z=10.0)
    client.home("XY")
    assert client.get_position() == {"x": 0.0, "y": 0.0, "z": 10.0}
    assert client.get_homed_axes() == "xy"


def test_get_axis_limits_returns_fixed_bounds():
    client = MockMoonrakerClient()
    assert client.get_axis_limits() == {"x": (0.0, 350.0), "y": (0.0, 350.0), "z": (0.0, 340.0)}


def test_gcode_does_not_raise():
    MockMoonrakerClient().gcode("G28")
