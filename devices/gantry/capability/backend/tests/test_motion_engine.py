"""Tests for MotionEngine's raise-XY-lower clearance-travel sequencing."""
from rxn_bench_gantry.motion_engine import MotionEngine

from tests.fakes import FakeMotionClient


def test_move_to_sequences_raise_then_xy_then_lower():
    client = FakeMotionClient()
    engine = MotionEngine(client)
    engine.move_to(x=100.0, y=50.0, z=10.0, clearance_z=75.0, speed=1000.0)

    assert [name for name, _ in client.calls] == ["move", "move", "move"]
    raise_args, xy_args, lower_args = (args for _, args in client.calls)
    assert raise_args == {"x": None, "y": None, "z": 75.0, "speed": 1000.0}
    assert xy_args == {"x": 100.0, "y": 50.0, "z": None, "speed": 1000.0}
    assert lower_args == {"x": None, "y": None, "z": 10.0, "speed": 1000.0}


def test_move_to_with_none_z_leaves_carriage_at_clearance_height():
    client = FakeMotionClient()
    engine = MotionEngine(client)
    engine.move_to(x=10.0, y=10.0, z=None, clearance_z=50.0)

    _, _, lower_args = (args for _, args in client.calls)
    assert lower_args["z"] is None


def test_jog_has_no_clearance_sequence():
    client = FakeMotionClient()
    engine = MotionEngine(client)
    engine.jog(dx=5.0, dy=-2.0, dz=1.0, speed=500.0)

    assert [name for name, _ in client.calls] == ["jog"]
    assert client.calls[0][1] == {"dx": 5.0, "dy": -2.0, "dz": 1.0, "speed": 500.0}


def test_move_is_a_single_direct_passthrough():
    client = FakeMotionClient()
    engine = MotionEngine(client)
    engine.move(z=42.0, speed=250.0)

    assert client.calls == [("move", {"x": None, "y": None, "z": 42.0, "speed": 250.0})]


def test_get_position_and_state_delegate_to_client():
    client = FakeMotionClient(x=1.0, y=2.0, z=3.0)
    engine = MotionEngine(client)

    assert engine.get_position() == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert engine.get_state() == "ready"
