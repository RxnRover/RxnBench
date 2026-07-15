"""Tests for GantryController: bounds enforcement, toolhead-aware limits, homing integration."""
import textwrap

import pytest

from rxn_bench_gantry.controller import GantryController
from rxn_bench_gantry.errors import (
    MotionLimitError,
    ToolheadNotMountedError,
    UnvalidatedGeometryError,
)
from rxn_bench_gantry.plate_geometry import PlateGeometry

from tests.fakes import FakeMotionClient

# Derived from the labware source of truth rather than hardcoded, so these
# tests don't silently break when a bundled plate's dimensions are re-measured
# (never hardcode plate dimensions outside labware/*.yaml - see CURRENT_STATE section 8).
_PLATE_HEIGHT_96 = PlateGeometry.load("96_well_standard").plate_height_mm
_WELL_DEPTH_96 = PlateGeometry.load("96_well_standard").well_depth_mm

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


# Bare-carriage bounds (no toolhead mounted)

def test_get_limits_format(ctrl):
    limits_str = ctrl.get_limits()
    parts = limits_str.split("|")
    assert len(parts) == 9  # 7 numeric fields + 2 crossbar (empty when unset)
    x_min, x_max, y_min, y_max, z_min, z_max, safe_clearance_z = [float(p) for p in parts[:7]]
    assert (x_min, x_max, y_min, y_max, z_min, z_max) == (0.0, 300.0, 0.0, 300.0, 0.0, 250.0)
    assert safe_clearance_z == pytest.approx(50.0)  # _BARE_CLEARANCE_Z_MM, no workspace loaded
    assert parts[7] == "" and parts[8] == ""        # crossbar model not configured -> empty


def test_get_safe_clearance_z_matches_get_limits_field(ctrl):
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    safe = float(ctrl.get_limits().split("|")[6])   # 7th field is safe_clearance_z
    assert ctrl.get_safe_clearance_z() == pytest.approx(safe)
    # origin_z(15) + 96-well plate height + default 5mm padding
    assert safe == pytest.approx(15.0 + _PLATE_HEIGHT_96 + 5.0)


def test_get_limits_includes_crossbar_geometry_when_configured(client):
    parts = _crossbar_ctrl(client).get_limits().split("|")
    assert len(parts) == 9
    assert float(parts[7]) == pytest.approx(_CROSSBAR_H)
    assert float(parts[8]) == pytest.approx(_CROSSBAR_T)


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


# Toolhead-aware bounds (footprint + tip offset compensation)

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


# Workspace-aware safe clearance height (dynamic, not a flat constant)

def test_safe_clearance_falls_back_to_bare_floor_without_workspace(ctrl, client):
    ctrl.move_to(100.0, 100.0, 100.0)
    assert client.calls[0][1]["z"] == pytest.approx(50.0)  # _BARE_CLEARANCE_Z_MM


def test_safe_clearance_uses_workspace_labware_height(ctrl, client):
    # plate1 sits at origin_z=15.0; its top = 15 + 96-well plate height, plus
    # the default 5mm padding, which beats the bare 50mm floor.
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.move_to(100.0, 100.0, 100.0)
    assert client.calls[0][1]["z"] == pytest.approx(15.0 + _PLATE_HEIGHT_96 + 5.0)


def test_safe_clearance_padding_is_configurable(client):
    ctrl = GantryController(
        client=client,
        x_min=0.0, x_max=300.0, y_min=0.0, y_max=300.0, z_min=0.0, z_max=250.0,
        z_clearance_padding_mm=20.0,
    )
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)
    ctrl.move_to(100.0, 100.0, 100.0)
    assert client.calls[0][1]["z"] == pytest.approx(15.0 + _PLATE_HEIGHT_96 + 20.0)


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


# Placeholder-geometry guard on well-targeted moves

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
    assert lower_call["z"] == pytest.approx(15.0 + _PLATE_HEIGHT_96)  # origin_z + plate_height_mm


# Engagement depth: blended toolhead z_engage + the docked well's own depth


def _dock_ph_probe(ctrl):
    """Load the 96-well bench, activate + mount a validated ph_probe, dock A1.

    Returns the well opening Z (origin_z + plate_height), the height the tip is
    left at by move_to_well - engage/disengage descend/ascend from here.
    """
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)  # 96_well_standard
    ctrl.set_toolhead("ph_probe")
    ctrl._toolhead_mgr.toolhead.geometry_validated = True
    ctrl.set_toolhead_mounted(True)
    ctrl.move_to_well("plate1/A1")
    return 15.0 + _PLATE_HEIGHT_96


def test_move_to_well_no_longer_refuses_deep_z_engage(ctrl, client):
    # A toolhead whose configured z_engage exceeds the target well's depth used
    # to be refused outright; now the move proceeds and the descent is capped a
    # safe margin above the bottom at engage time instead (tested below).
    # geometry_validated is forced True to isolate this from the separate
    # unvalidated-geometry gate (ph_probe ships with it false).
    ctrl.load_workspace_from_yaml(_SIMPLE_WORKSPACE_YAML)  # 96_well_standard
    ctrl.set_toolhead("ph_probe")
    th = ctrl._toolhead_mgr.toolhead
    th.geometry_validated = True
    th.z_engage = _WELL_DEPTH_96 + 5.0  # deeper than the well can accommodate
    ctrl.set_toolhead_mounted(True)
    ctrl.move_to_well("plate1/A1")  # no longer raises
    assert any(name == "move" for name, _ in client.calls)


def test_engage_tool_blends_requested_depth_with_docked_well(ctrl, client):
    # Normal case: requested depth shallower than the well. The tip descends to
    # the mean of the requested depth and the well's own depth - deeper than the
    # bare request, but still short of the bottom.
    opening = _dock_ph_probe(ctrl)
    client.calls.clear()
    ctrl.engage_tool(depth=20.0)  # < well_depth (36)
    expected = (20.0 + _WELL_DEPTH_96) / 2  # 28.0, within the safe cap
    assert client.calls[-1][1]["z"] == pytest.approx(opening - expected)


def test_engage_tool_caps_descent_above_well_bottom(ctrl, client):
    # Over-deep case: requested depth (40) deeper than the well (36). The blend
    # would reach past the bottom, so it is capped at well_depth - margin: the
    # tip stops a fixed gap above the bottom rather than being refused.
    opening = _dock_ph_probe(ctrl)
    client.calls.clear()
    ctrl.engage_tool(depth=40.0)
    capped = _WELL_DEPTH_96 - ctrl._engage_bottom_margin_mm
    assert client.calls[-1][1]["z"] == pytest.approx(opening - capped)


def test_disengage_returns_tip_to_well_opening(ctrl):
    # engage then disengage with the same requested depth is symmetric (both use
    # the same blended depth), so the tip ends exactly back at the well opening
    # instead of drifting lower each cycle.
    opening = _dock_ph_probe(ctrl)
    ctrl.engage_tool(depth=40.0)
    ctrl.disengage_tool(depth=40.0)
    assert ctrl.get_position()["z"] == pytest.approx(opening)


def test_engage_tool_uses_raw_depth_after_plain_move_clears_well(ctrl, client):
    # A plain move_to since the last well drops the docked-well context, so
    # engage_tool falls back to the literal requested depth (nothing to blend).
    _dock_ph_probe(ctrl)
    ctrl.move_to(100.0, 100.0, 50.0)   # clears _current_well_label
    client.calls.clear()
    ctrl.engage_tool(depth=5.0)
    assert client.calls[-1][1]["z"] == pytest.approx(45.0)  # raw 5mm descent


def test_move_to_well_override_unvalidated_still_allows_the_move(ctrl, client):
    # The toolhead calibration wizard relies on override_unvalidated to visit
    # corner wells with an as-yet-unmeasured toolhead (its geometry_validated is
    # false); the move must proceed.
    ctrl.load_workspace_from_yaml(textwrap.dedent("""\
        name: shallow_bench
        calibration_reference_well: plate1/A1
        plates:
          - id: plate1
            plate_type: 24_well_standard
            origin: {x: 100.0, y: 100.0, z: 15.0}
            orientation: standard
    """))
    ctrl.set_toolhead("ph_probe")  # ships geometry_validated=false
    ctrl.set_toolhead_mounted(True)
    ctrl.move_to_well("plate1/A1", override_unvalidated=True)
    assert any(name == "move" for name, _ in client.calls)


def test_move_to_well_bare_carriage_has_no_engagement_blend(ctrl):
    # No active toolhead -> nothing to blend against; the well move just works.
    ctrl.load_workspace_from_yaml(textwrap.dedent("""\
        name: shallow_bench
        calibration_reference_well: plate1/A1
        plates:
          - id: plate1
            plate_type: 24_well_standard
            origin: {x: 100.0, y: 100.0, z: 15.0}
            orientation: standard
    """))
    ctrl.move_to_well("plate1/A1")  # no toolhead active -> fine


# Toolhead tip calibration

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


# Homing / saved-state integration

def test_save_requires_calibration(ctrl):
    with pytest.raises(RuntimeError, match="not been calibrated"):
        ctrl.save_and_park()


def test_save_allowed_after_homing(ctrl):
    ctrl.home_auto()
    ctrl.save_and_park()
    assert ctrl.has_saved_state


# Workspace YAML + labware accessors

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


# Intra-plate travel optimization: same-plate well moves skip the full-deck
# clearance and travel at just the target plate's own (uniform) top height.

_TWO_PLATE_YAML = textwrap.dedent("""\
    name: two_plate
    calibration_reference_well: short/A1
    plates:
      - id: short
        plate_type: 96_well_standard
        origin: {x: 100.0, y: 100.0, z: 0.0}
        orientation: standard
      - id: tall
        plate_type: 96_well_standard
        origin: {x: 100.0, y: 250.0, z: 50.0}
        orientation: standard
""")

_SHORT_TOP = _PLATE_HEIGHT_96          # origin_z 0 + plate height
_TALL_TOP = 50.0 + _PLATE_HEIGHT_96    # origin_z 50 + plate height
_FULL_CLEARANCE = _TALL_TOP + 5.0      # tallest deck plate + default 5mm padding
_INTRA_SHORT = _SHORT_TOP + 5.0        # just the short plate + padding


def test_move_to_well_first_move_uses_full_clearance(ctrl, client):
    # Carriage starts at home (0,0) - not over any plate - so clear the deck.
    ctrl.load_workspace_from_yaml(_TWO_PLATE_YAML)
    ctrl.move_to_well("short/A1")
    assert client.calls[0][1]["z"] == pytest.approx(_FULL_CLEARANCE)


def test_move_to_well_same_plate_uses_intra_plate_clearance(ctrl, client):
    ctrl.load_workspace_from_yaml(_TWO_PLATE_YAML)
    ctrl.move_to_well("short/A1")           # now positioned over 'short'
    client.calls.clear()
    ctrl.move_to_well("short/A2")           # same plate -> only clear 'short'
    assert client.calls[0][1]["z"] == pytest.approx(_INTRA_SHORT)
    assert _INTRA_SHORT < _FULL_CLEARANCE   # the whole point: a much lower raise


def test_move_to_well_cross_plate_uses_full_clearance(ctrl, client):
    ctrl.load_workspace_from_yaml(_TWO_PLATE_YAML)
    ctrl.move_to_well("short/A1")           # over 'short'
    client.calls.clear()
    ctrl.move_to_well("tall/A1")            # hop to 'tall' -> full deck clearance
    assert client.calls[0][1]["z"] == pytest.approx(_FULL_CLEARANCE)


def test_plain_move_to_always_uses_full_clearance(ctrl, client):
    # A bare move_to has no plate context and must clear the whole deck even
    # when the carriage happens to sit over a short plate.
    ctrl.load_workspace_from_yaml(_TWO_PLATE_YAML)
    ctrl.move_to_well("short/A1")
    client.calls.clear()
    ctrl.move_to(120.0, 120.0, 60.0)
    assert client.calls[0][1]["z"] == pytest.approx(_FULL_CLEARANCE)


# X-gantry crossbar collision check: the bar spans X at the carriage's Y, so a
# taller plate sharing the target's Y-row can be hit by the descending bar even
# though the tip is clear. Off (geometry unset) unless configured.

_CROSSBAR_H = 40.0   # crossbar underside sits 40mm above the tip
_CROSSBAR_T = 20.0   # crossbar is 20mm thick in Y


def _crossbar_ctrl(client):
    return GantryController(
        client=client,
        x_min=0.0, x_max=350.0, y_min=0.0, y_max=350.0, z_min=0.0, z_max=250.0,
        crossbar_clearance_above_tip_mm=_CROSSBAR_H,
        crossbar_y_thickness_mm=_CROSSBAR_T,
    )


# short plate (top = plate_height) beside a much taller plate in the SAME Y-row.
_SAME_ROW_YAML = textwrap.dedent("""\
    name: same_row
    calibration_reference_well: short/A1
    plates:
      - id: short
        plate_type: 96_well_standard
        origin: {x: 80.0, y: 150.0, z: 0.0}
        orientation: standard
      - id: tall
        plate_type: 96_well_standard
        origin: {x: 250.0, y: 150.0, z: 60.0}
        orientation: standard
""")


def test_crossbar_refuses_dock_when_taller_plate_shares_y_row(client):
    ctrl = _crossbar_ctrl(client)
    ctrl.load_workspace_from_yaml(_SAME_ROW_YAML)
    # tall top = 60 + plate_height; docking at short's opening puts the bar at
    # opening + H, well below the tall plate -> refuse before any motion.
    with pytest.raises(MotionLimitError, match="crossbar"):
        ctrl.move_to_well("short/A1")
    assert client.calls == []


def test_crossbar_allows_dock_when_taller_plate_is_a_different_y_row(client):
    ctrl = _crossbar_ctrl(client)
    ctrl.load_workspace_from_yaml(textwrap.dedent("""\
        name: different_row
        calibration_reference_well: short/A1
        plates:
          - id: short
            plate_type: 96_well_standard
            origin: {x: 80.0, y: 100.0, z: 0.0}
            orientation: standard
          - id: tall
            plate_type: 96_well_standard
            origin: {x: 250.0, y: 260.0, z: 60.0}
            orientation: standard
    """))
    ctrl.move_to_well("short/A1")  # tall plate is out of the crossbar's Y band
    assert any(name == "move" for name, _ in client.calls)


def test_crossbar_disabled_when_geometry_unset(client):
    ctrl = GantryController(
        client=client, x_min=0.0, x_max=350.0, y_min=0.0, y_max=350.0,
        z_min=0.0, z_max=250.0,
    )  # no crossbar params -> the whole check is inert
    ctrl.load_workspace_from_yaml(_SAME_ROW_YAML)
    ctrl.move_to_well("short/A1")  # would refuse if enabled; disabled -> fine
    assert any(name == "move" for name, _ in client.calls)


def test_crossbar_refuses_engage_that_lowers_bar_into_a_taller_row_plate(client):
    ctrl = _crossbar_ctrl(client)
    ctrl.load_workspace_from_yaml(textwrap.dedent("""\
        name: row
        calibration_reference_well: short/A1
        plates:
          - id: short
            plate_type: 96_well_standard
            origin: {x: 80.0, y: 150.0, z: 0.0}
            orientation: standard
          - id: mid
            plate_type: 96_well_standard
            origin: {x: 250.0, y: 150.0, z: 30.0}
            orientation: standard
    """))
    # mid top = 30 + plate_height. Docking at short's opening keeps the bar above
    # mid (allowed), but engaging deeper drives it down into mid -> refuse.
    ctrl.move_to_well("short/A1")
    with pytest.raises(MotionLimitError, match="crossbar"):
        ctrl.engage_tool(depth=20.0)
