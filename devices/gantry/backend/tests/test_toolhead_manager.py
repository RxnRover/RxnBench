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


def test_ph_probe_geometry_is_unvalidated_placeholder():
    mgr = ToolheadManager()
    mgr.set_toolhead("ph_probe")
    assert mgr.toolhead.geometry_validated is False


def test_set_toolhead_warns_on_unvalidated_geometry(caplog):
    mgr = ToolheadManager()
    with caplog.at_level("WARNING"):
        mgr.set_toolhead("ph_probe")
    assert any("unvalidated" in rec.message for rec in caplog.records)


def test_set_toolhead_does_not_warn_when_validated(tmp_path, monkeypatch, caplog):
    import rxn_bench_gantry.toolhead_config as toolhead_config

    toolhead_dir = tmp_path / "measured_probe"
    toolhead_dir.mkdir()
    (toolhead_dir / "measured_probe_toolhead.yaml").write_text("""
name: measured_probe
display_name: Measured Probe
geometry:
  footprint_x: 10.0
  footprint_y: 10.0
  offset_x: 0.0
  offset_y: 0.0
  tip_offset_z: 5.0
  z_engage: 1.0
""")
    monkeypatch.setattr(toolhead_config, "_TOOLHEADS_DIR", tmp_path)

    mgr = ToolheadManager()
    with caplog.at_level("WARNING"):
        mgr.set_toolhead("measured_probe")
    assert mgr.toolhead.geometry_validated is True
    assert not caplog.records
