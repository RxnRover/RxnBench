"""Smoke tests for ToolheadManager YAML loading."""
import pytest

from rxn_bench_gantry.toolhead_manager import ToolheadManager


def test_list_toolheads_returns_entries():
    entries = ToolheadManager.list_toolheads()
    assert isinstance(entries, list)
    assert len(entries) >= 1
    for name, display_name in entries:
        assert isinstance(name, str) and name
        assert isinstance(display_name, str) and display_name


def test_set_toolhead_loads_geometry():
    mgr = ToolheadManager()
    entries = ToolheadManager.list_toolheads()
    assert entries
    name, _ = entries[0]
    mgr.set_toolhead(name)
    assert mgr.name == name
    th = mgr.toolhead
    assert th is not None
    assert th.footprint_x > 0
    assert th.footprint_y > 0
    assert th.tip_offset_z >= 0


def test_clear_toolhead():
    mgr = ToolheadManager()
    entries = ToolheadManager.list_toolheads()
    mgr.set_toolhead(entries[0][0])
    mgr.clear_toolhead()
    assert mgr.toolhead is None
    assert mgr.name == ""
    assert not mgr.mounted


def test_set_mounted():
    mgr = ToolheadManager()
    assert not mgr.mounted
    mgr.set_mounted(True)
    assert mgr.mounted
    mgr.set_mounted(False)
    assert not mgr.mounted


def test_sensor_type_exposed():
    mgr = ToolheadManager()
    entries = ToolheadManager.list_toolheads()
    name, _ = entries[0]
    mgr.set_toolhead(name)
    assert mgr.sensor_type == "ph"


def test_sensor_type_cleared():
    mgr = ToolheadManager()
    entries = ToolheadManager.list_toolheads()
    mgr.set_toolhead(entries[0][0])
    mgr.clear_toolhead()
    assert mgr.sensor_type is None


def test_unknown_toolhead_raises():
    mgr = ToolheadManager()
    with pytest.raises(Exception):
        mgr.set_toolhead("does_not_exist_xyz")
