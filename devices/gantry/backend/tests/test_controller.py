"""Tests for GantryController: bounds enforcement, toolhead-aware limits, homing integration."""
import textwrap

import pytest

from rxn_bench_gantry.controller import GantryController
from rxn_bench_gantry.errors import (
    MotionLimitError,
    ToolheadNotMountedError,
    UnvalidatedGeometryError,
)

from tests.fakes import FakeMotionClient

_SIMPLE_WORKSPACE_YAML = textwrap.dedent("""\
    name: test_bench
    calibration_reference_well: plate1/A1
    plates:
      - id: plate1
        plate_type: 96_well_standard
        origin:
          x: 113.88
          y: 142.74
          z: 15.0
        orientation: standard
""")


@pytest.fixture
def client():
    return FakeMotionClient()


@pytest.fixture
def ctrl(client):
    return GantryController(
        client=client,
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
    ctrl.set_toolhead("ph_probe")  # offset_x=offset_y=0 by default now, tip_x=tip_y=0 (unmeasured)
    ctrl._toolhead_mgr.toolhead.offset_y = -35.0  # simulate a measured mount offset
    ctrl.move_to(100.0, 150.0, 150.0)
    xy_args = client.calls[1][1]
    assert xy_args["x"] == pytest.approx(100.0)  # offset_x + tip_x == 0
    assert xy_args["y"] == pytest.approx(115.0)  # 150 + (offset_y + tip_y) == 150 - 35


def test_toolhead_tip_offset_z_raises_safe_clearance_height(ctrl, client):
    ctrl.set_toolhead("ph_probe")
    ctrl._toolhead_mgr.toolhead.tip_offset_z = 110.0  # deeper than the default clearance_z=50mm
    ctrl.move_to(100.0, 150.0, 150.0)
    assert client.calls[0][1]["z"] == 110.0  # max(clearance_z=50, tip_offset_z=110)


# ---------------------------------------------------------------------------
# Workspace-aware safe clearance height (dynamic, not a flat constant)
# ---------------------------------------------------------------------------

def test_safe_clearance_falls_back_to_bare_floor_without_workspace(ctrl, client):
    ctrl.move_to(100.0, 100.0, 100.0)
    assert client.calls[0][1]["z"] == pytest.approx(50.0)  # _BARE_CLEARANCE_Z_MM


def test_safe_clearance_uses_workspace_labware_height(ctrl, client):
    # plate1 sits at origin_z=15.0; 96_well_standard's plate_height_mm=39 ->
    # top=54.0, plus the default 5mm padding = 59.0, which beats the bare
    # 50mm floor.
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.move_to(100.0, 100.0, 100.0)
    assert client.calls[0][1]["z"] == pytest.approx(59.0)


def test_safe_clearance_padding_is_configurable(client):
    ctrl = GantryController(
        client=client,
        x_min=0.0, x_max=300.0, y_min=0.0, y_max=300.0, z_min=0.0, z_max=250.0,
        z_clearance_padding_mm=20.0,
    )
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.move_to(100.0, 100.0, 100.0)
    assert client.calls[0][1]["z"] == pytest.approx(15.0 + 39.0 + 20.0)


def test_safe_clearance_ignores_padding_when_no_labware_loaded(ctrl, client):
    # Padding is only meaningful relative to a measured labware height - it
    # must not become a phantom floor of its own when the deck is empty.
    ctrl.move_to(100.0, 100.0, 100.0)
    assert client.calls[0][1]["z"] == pytest.approx(50.0)


def test_toolhead_tip_below_z_min_raises(ctrl):
    ctrl.set_toolhead("ph_probe")
    ctrl._toolhead_mgr.toolhead.tip_offset_z = 110.0  # tip sits 110mm below the carriage
    with pytest.raises(MotionLimitError, match="tool tip"):
        ctrl.move_to(100.0, 150.0, 50.0)  # tip would sit at 50 - 110 = -60mm, below z_min=0


def test_clear_toolhead_restores_bare_carriage_bounds(ctrl):
    ctrl.set_toolhead("ph_probe")
    ctrl.clear_toolhead()
    ctrl.move_to(290.0, 100.0, 150.0)  # no longer rejected once footprint is gone


def test_set_toolhead_preserves_saved_homing_state(ctrl):
    """Switching the active head is software-only: with several heads mounted
    at once, activation does not change the carriage, so homing survives -
    scripts can alternate heads mid-run and still save_and_park at the end."""
    ctrl.set_toolhead("ph_probe")
    ctrl.set_toolhead_mounted(True)
    ctrl.home_auto()
    ctrl.save_and_park()
    assert ctrl.has_saved_state

    ctrl.set_toolhead("ph_probe")
    assert ctrl.has_saved_state


def test_mounting_change_invalidates_saved_homing_state(ctrl):
    """Adding/removing hardware changes the carriage envelope -> re-home."""
    ctrl.home_auto()
    ctrl.save_and_park()
    ctrl.set_toolhead("ph_probe")
    assert ctrl.has_saved_state

    ctrl.set_toolhead_mounted(True)
    assert not ctrl.has_saved_state


def test_reconfirming_mounted_head_preserves_homing(ctrl):
    """Idempotent confirm: a script's mount_toolhead at startup must not
    invalidate the homing the operator just did."""
    ctrl.set_toolhead("ph_probe")
    ctrl.set_toolhead_mounted(True)
    ctrl.home_auto()
    ctrl.save_and_park()
    assert ctrl.has_saved_state

    ctrl.set_toolhead_mounted(True)  # already confirmed -> no-op
    assert ctrl.has_saved_state


def test_clear_toolhead_of_mounted_head_invalidates_homing(ctrl):
    ctrl.set_toolhead("ph_probe")
    ctrl.set_toolhead_mounted(True)
    ctrl.home_auto()
    ctrl.save_and_park()
    assert ctrl.has_saved_state

    ctrl.clear_toolhead()  # physical removal
    assert not ctrl.has_saved_state
    assert ctrl.get_mounted_toolheads() == []


# ---------------------------------------------------------------------------
# Placeholder-geometry guard on well-targeted moves
# ---------------------------------------------------------------------------

def test_move_to_well_refuses_unvalidated_toolhead_geometry(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")  # ph_probe_toolhead.yaml sets geometry_validated: false
    ctrl.set_toolhead_mounted(True)
    with pytest.raises(UnvalidatedGeometryError, match="unvalidated"):
        ctrl.move_to_well("plate1/A1")


def test_move_to_well_override_unvalidated_proceeds(ctrl, client):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")
    ctrl.set_toolhead_mounted(True)
    ctrl.move_to_well("plate1/A1", override_unvalidated=True)
    assert any(name == "move" for name, _ in client.calls)


def test_move_to_well_reports_expected_and_actual_position(ctrl):
    # Bare carriage: no toolhead offset, so actual should land exactly on
    # the well's expected nominal position - this is the log data used to
    # spot a mismatch between hand-computed geometry and real hardware.
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    nominal_x, nominal_y, nominal_z = ctrl._workspace_mgr.resolve_well("plate1/A1")
    result = ctrl.move_to_well("plate1/A1")
    assert result["expected_well_x"] == pytest.approx(nominal_x)
    assert result["expected_well_y"] == pytest.approx(nominal_y)
    assert result["expected_well_z"] == pytest.approx(nominal_z)
    assert result["actual_x"] == pytest.approx(nominal_x)
    assert result["actual_y"] == pytest.approx(nominal_y)
    assert result["actual_z"] == pytest.approx(nominal_z)


def test_move_to_well_actual_position_includes_toolhead_offset(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")  # offset_x=offset_y=0 by default now - measured via calibration
    ctrl._toolhead_mgr.toolhead.offset_y = -35.0  # simulate a measured mount offset
    ctrl.set_toolhead_mounted(True)
    nominal_x, nominal_y, nominal_z = ctrl._workspace_mgr.resolve_well("plate1/A1")
    result = ctrl.move_to_well("plate1/A1", override_unvalidated=True)
    assert result["expected_well_x"] == pytest.approx(nominal_x)
    assert result["expected_well_y"] == pytest.approx(nominal_y)
    assert result["actual_x"] == pytest.approx(nominal_x)
    assert result["actual_y"] == pytest.approx(nominal_y - 35.0)
    # z is not touched by toolhead XY offset - the carriage still docks at
    # the well's opening height.
    assert result["actual_z"] == pytest.approx(nominal_z)


def test_move_to_well_docks_at_plate_top_not_clearance_height(ctrl, client):
    # Before this, move_to_well left Z at the generic clearance height, which
    # made engage_tool's fixed z_engage descent physically meaningless once
    # clearance height became workspace-dependent (Phase 1) - a plate shared
    # with a taller container would raise clearance well above this plate's
    # own top surface, and z_engage would then stop short of the well.
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.move_to_well("plate1/A1")
    lower_call = [c for name, c in client.calls if name == "move"][-1]
    assert lower_call["z"] == pytest.approx(15.0 + 39.0)  # origin_z + plate_height_mm


# ---------------------------------------------------------------------------
# Engagement-depth safety: toolhead z_engage vs. the target well's own depth
# ---------------------------------------------------------------------------

def test_move_to_well_rejects_z_engage_deeper_than_well(ctrl):
    # 24_well_standard's well_depth_mm=17.4; ph_probe's z_engage=25 would
    # punch through the bottom of this shallower well.
    ctrl.load_workspace_from_yaml(textwrap.dedent("""\
        name: shallow_bench
        calibration_reference_well: plate1/A1
        plates:
          - id: plate1
            plate_type: 24_well_standard
            origin: {x: 100.0, y: 100.0, z: 15.0}
            orientation: standard
    """))
    ctrl.set_toolhead("ph_probe")
    ctrl.set_toolhead_mounted(True)
    with pytest.raises(MotionLimitError, match="collide with the well bottom"):
        ctrl.move_to_well("plate1/A1", override_unvalidated=True)


def test_move_to_well_allows_z_engage_within_well_depth(ctrl, client):
    # 96_well_standard's well_depth_mm=36 comfortably covers ph_probe's
    # z_engage=25.
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")
    ctrl.set_toolhead_mounted(True)
    ctrl.move_to_well("plate1/A1", override_unvalidated=True)
    assert any(name == "move" for name, _ in client.calls)


def test_move_to_well_skips_engagement_check_without_toolhead(ctrl):
    # Bare carriage has no z_engage to check against - only a mounted
    # toolhead's own configured engagement depth is meaningful here.
    ctrl.load_workspace_from_yaml(textwrap.dedent("""\
        name: shallow_bench
        calibration_reference_well: plate1/A1
        plates:
          - id: plate1
            plate_type: 24_well_standard
            origin: {x: 100.0, y: 100.0, z: 15.0}
            orientation: standard
    """))
    ctrl.move_to_well("plate1/A1")  # no toolhead active -> not refused


# ---------------------------------------------------------------------------
# Toolhead tip calibration
# ---------------------------------------------------------------------------

def test_calibrate_toolhead_tip_single_well(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")  # offset_x=offset_y=0 by default now
    ctrl._toolhead_mgr.toolhead.offset_y = -35.0  # simulate a measured mount offset
    nominal_x, nominal_y, _z = ctrl._workspace_mgr.resolve_well("plate1/A1")
    result = ctrl.calibrate_toolhead_tip(nominal_x + 2.0, nominal_y - 1.0, "plate1/A1")
    th = ctrl.get_toolhead()
    assert th.tip_x == pytest.approx(2.0)          # measured - nominal - offset_x(0)
    assert th.tip_y == pytest.approx(-1.0 + 35.0)  # measured - nominal - offset_y(-35)
    assert th.geometry_validated is True
    assert result["nominal_x"] == pytest.approx(nominal_x)
    assert result["nominal_y"] == pytest.approx(nominal_y)
    assert result["tip_x"] == pytest.approx(2.0)
    assert result["tip_y"] == pytest.approx(34.0)


def test_calibrate_toolhead_tip_averages_multiple_wells(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")
    ctrl._toolhead_mgr.toolhead.offset_y = -35.0
    # A1/A12/H1/H12 are this plate's 4 corner wells; by grid symmetry their
    # nominal average is exactly the plate's own origin (113.88, 142.74).
    wells = "plate1/A1|plate1/A12|plate1/H1|plate1/H12"
    result = ctrl.calibrate_toolhead_tip(113.88 + 5.0, 142.74 - 3.0, wells)
    th = ctrl.get_toolhead()
    assert th.tip_x == pytest.approx(5.0)
    assert th.tip_y == pytest.approx(-3.0 + 35.0)
    assert result["nominal_x"] == pytest.approx(113.88)
    assert result["nominal_y"] == pytest.approx(142.74)


def test_calibrate_toolhead_tip_requires_a_well(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")
    with pytest.raises(RuntimeError, match="at least one well"):
        ctrl.calibrate_toolhead_tip(0.0, 0.0, "")


def test_calibrate_toolhead_tip_requires_active_toolhead(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    with pytest.raises(RuntimeError, match="No active toolhead"):
        ctrl.calibrate_toolhead_tip(0.0, 0.0, "plate1/A1")


def test_move_to_well_with_no_toolhead_is_not_refused(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.move_to_well("plate1/A1")  # bare carriage has no geometry to validate


def test_move_to_well_refuses_unconfirmed_toolhead(ctrl):
    """Using a head for well work requires its one-time mount confirmation."""
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")  # active but never confirmed mounted
    with pytest.raises(ToolheadNotMountedError, match="not confirmed mounted"):
        ctrl.move_to_well("plate1/A1", override_unvalidated=True)


def test_move_to_well_allowed_after_switching_back_to_confirmed_head(ctrl, client):
    """The dual-head script flow: confirm once, switch freely, keep working."""
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.set_toolhead("ph_probe")
    ctrl.set_toolhead_mounted(True)
    ctrl.set_toolhead("ph_probe")  # activation switch - confirmation persists
    ctrl.move_to_well("plate1/A1", override_unvalidated=True)
    assert any(name == "move" for name, _ in client.calls)


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


# ---------------------------------------------------------------------------
# Workspace YAML + labware accessors
# ---------------------------------------------------------------------------

def test_get_workspace_yaml_empty_without_workspace(ctrl):
    assert ctrl.get_workspace_yaml() == ""


def test_get_workspace_yaml_reflects_yaml_load(ctrl):
    import yaml
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    data = yaml.safe_load(ctrl.get_workspace_yaml())
    assert data["name"] == "test_bench"
    assert data["plates"][0]["plate_type"] == "96_well_standard"


def test_get_labware_yaml_contains_bundled_plates(ctrl):
    import yaml
    labware = yaml.safe_load(ctrl.get_labware_yaml())
    assert "96_well_standard" in labware
    plate = labware["96_well_standard"]
    assert plate["rows"] == 8 and plate["columns"] == 12
    # Footprint fields are required by the frontend deck canvas.
    assert plate["width_mm"] == pytest.approx(127.76)
    assert plate["height_mm"] == pytest.approx(85.48)
