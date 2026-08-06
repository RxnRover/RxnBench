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
    entries = ToolheadManager.list_toolheads()
    mgr.set_toolhead(entries[0][0])
    assert not mgr.mounted
    mgr.set_mounted(True)
    assert mgr.mounted
    mgr.set_mounted(False)
    assert not mgr.mounted


def test_mount_confirmation_survives_switching():
    """Mount state is per-head: switching the active toolhead must not clear it,
    or scripts alternating between two mounted heads would need an operator."""
    mgr = ToolheadManager()
    entries = ToolheadManager.list_toolheads()
    mgr.set_toolhead(entries[0][0])
    mgr.set_mounted(True)
    mgr.set_toolhead(entries[0][0])  # activation switch is a software-only change
    assert mgr.mounted
    assert mgr.mounted_toolheads == [entries[0][0]]


def test_set_mounted_reports_actual_changes_only():
    """confirm/clear are idempotent - the bool return drives homing invalidation."""
    mgr = ToolheadManager()
    entries = ToolheadManager.list_toolheads()
    assert mgr.set_mounted(True) is False  # no active head -> no-op
    mgr.set_toolhead(entries[0][0])
    assert mgr.set_mounted(True) is True
    assert mgr.set_mounted(True) is False  # re-confirming changes nothing
    assert mgr.set_mounted(False) is True
    assert mgr.set_mounted(False) is False


def test_mount_states_tracked_per_head(tmp_path, monkeypatch):
    """Two heads mounted at once: each keeps its own confirmation."""
    import rxn_bench_gantry.toolhead_config as toolhead_config

    for name in ("head_a", "head_b"):
        d = tmp_path / name
        d.mkdir()
        (d / f"{name}_toolhead.yaml").write_text(f"""
name: {name}
display_name: {name.title()}
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
    mgr.set_toolhead("head_a")
    mgr.set_mounted(True)
    mgr.set_toolhead("head_b")
    assert not mgr.mounted                       # b not yet confirmed
    mgr.set_mounted(True)
    assert mgr.mounted_toolheads == ["head_a", "head_b"]

    mgr.set_toolhead("head_a")                   # switch back, still confirmed
    assert mgr.mounted

    mgr.clear_toolhead()                         # physically remove head_a
    assert mgr.mounted_toolheads == ["head_b"]


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


# Calibration timestamp

def test_new_toolhead_has_no_calibration_timestamp():
    mgr = ToolheadManager()
    mgr.set_toolhead("ph_probe")
    assert mgr.toolhead.calibrated_at == ""


def test_set_tip_offset_stamps_calibrated_at():
    mgr = ToolheadManager()
    mgr.set_toolhead("ph_probe")
    mgr.set_tip_offset(1.0, 2.0)
    assert mgr.toolhead.calibrated_at != ""


def test_set_tip_offset_z_stamps_calibrated_at():
    mgr = ToolheadManager()
    mgr.set_toolhead("ph_probe")
    mgr.set_tip_offset_z(3.0)
    assert mgr.toolhead.calibrated_at != ""


def test_calibrated_at_persists_across_toolhead_switch_and_restore(tmp_path, monkeypatch):
    import rxn_bench_gantry.toolhead_config as toolhead_config

    for name in ("probe_a", "probe_b"):
        d = tmp_path / name
        d.mkdir()
        (d / f"{name}_toolhead.yaml").write_text(f"""
name: {name}
display_name: {name.title()}
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
    mgr.set_toolhead("probe_a")
    mgr.set_tip_offset(1.0, 2.0)
    stamped = mgr.toolhead.calibrated_at
    assert stamped != ""

    mgr.set_toolhead("probe_b")
    assert mgr.toolhead.calibrated_at == ""  # different head, no calibration of its own

    mgr.set_toolhead("probe_a")  # switch back
    assert mgr.toolhead.calibrated_at == stamped

    # A fresh manager (simulating a server restart) restores it from disk too.
    mgr2 = ToolheadManager()
    mgr2.set_toolhead("probe_a")
    assert mgr2.toolhead.calibrated_at == stamped
