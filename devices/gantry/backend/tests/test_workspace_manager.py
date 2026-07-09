"""Tests for WorkspaceManager: load, load_from_yaml, resolve_well, orientation."""
import textwrap
import pytest

from rxn_bench_gantry.plate_geometry import PlateGeometry
from rxn_bench_gantry.workspace_manager import WorkspaceManager

_PLATE_HEIGHT_96 = PlateGeometry.load("96_well_standard").plate_height_mm


SIMPLE_YAML = textwrap.dedent("""\
    name: test_bench
    calibration_reference_well: plates/A1
    plates:
      - id: plates
        plate_type: 96_well_standard
        origin:
          x: 50.0
          y: 30.0
          z: 15.0
        orientation: standard
      - id: rotated
        plate_type: 96_well_standard
        origin:
          x: 200.0
          y: 30.0
          z: 15.0
        orientation: rotated_90
""")


@pytest.fixture
def mgr():
    m = WorkspaceManager()
    m.load_from_yaml(SIMPLE_YAML)
    return m


def test_load_from_yaml_sets_name(mgr):
    assert mgr.name == "test_bench"


def test_resolve_requires_workspace():
    m = WorkspaceManager()
    with pytest.raises(RuntimeError, match="No workspace"):
        m.resolve_well("A1")


def test_short_label_uses_first_plate(mgr):
    x1, y1, z1 = mgr.resolve_well("A1")
    x2, y2, z2 = mgr.resolve_well("plates/A1")
    assert (x1, y1, z1) == pytest.approx((x2, y2, z2))


def test_a1_position_standard(mgr):
    # origin is the centre of the plate's footprint, not its corner.
    x, y, z = mgr.resolve_well("plates/A1")
    assert x == pytest.approx(50.0 + 14.38 - 127.76 / 2)
    assert y == pytest.approx(30.0 + 11.24 - 85.48 / 2)
    # z is the plate's top surface (the well's opening), not the raw
    # origin_z the plate is mounted at.
    assert z == pytest.approx(15.0 + _PLATE_HEIGHT_96)


def test_a2_advances_x_by_spacing(mgr):
    x1, _, _ = mgr.resolve_well("plates/A1")
    x2, _, _ = mgr.resolve_well("plates/A2")
    assert x2 - x1 == pytest.approx(9.0)


def test_b1_advances_y_by_spacing(mgr):
    _, y1, _ = mgr.resolve_well("plates/A1")
    _, y2, _ = mgr.resolve_well("plates/B1")
    assert y2 - y1 == pytest.approx(9.0)


def test_rotated_a1_position(mgr):
    # origin is the footprint centre; A1's offset from centre is rotated
    # -90 degrees (dx, dy) -> (-dy, dx) around that fixed pivot point.
    centre_dx = 14.38 - 127.76 / 2
    centre_dy = 11.24 - 85.48 / 2
    x, y, z = mgr.resolve_well("rotated/A1")
    assert x == pytest.approx(200.0 + (-centre_dy))
    assert y == pytest.approx(30.0 + centre_dx)
    assert z == pytest.approx(15.0 + _PLATE_HEIGHT_96)


def test_rotated_a2_advances_in_y(mgr):
    _, y1, _ = mgr.resolve_well("rotated/A1")
    _, y2, _ = mgr.resolve_well("rotated/A2")
    assert y2 - y1 == pytest.approx(9.0)


def test_rotated_b1_retreats_in_x(mgr):
    x1, _, _ = mgr.resolve_well("rotated/A1")
    x2, _, _ = mgr.resolve_well("rotated/B1")
    assert x1 - x2 == pytest.approx(9.0)


def test_unknown_plate_id_raises(mgr):
    with pytest.raises(KeyError):
        mgr.resolve_well("nonexistent/A1")


# ---------------------------------------------------------------------------
# get_well_depth - drives the engagement-depth safety check in move_to_well
# ---------------------------------------------------------------------------

def test_get_well_depth_matches_plate_type(mgr):
    plate_96 = PlateGeometry.load("96_well_standard")
    assert mgr.get_well_depth("plates/A1") == pytest.approx(plate_96.well_depth_mm)


def test_get_well_depth_requires_workspace():
    with pytest.raises(RuntimeError, match="No workspace"):
        WorkspaceManager().get_well_depth("A1")


def test_get_well_depth_unknown_plate_raises(mgr):
    with pytest.raises(KeyError):
        mgr.get_well_depth("nonexistent/A1")


def test_load_from_yaml_clears_geometry_cache(mgr):
    mgr.load_from_yaml(SIMPLE_YAML)
    assert mgr.name == "test_bench"


def test_clear_resets_workspace(mgr):
    mgr.clear()
    assert mgr.name == ""
    with pytest.raises(RuntimeError):
        mgr.resolve_well("A1")


def test_to_yaml_empty_when_nothing_loaded():
    assert WorkspaceManager().to_yaml() == ""


def test_to_yaml_round_trips_through_load_from_yaml(mgr):
    import yaml
    data = yaml.safe_load(mgr.to_yaml())
    assert data["name"] == "test_bench"
    assert {p["id"] for p in data["plates"]} == {"plates", "rotated"}


# ---------------------------------------------------------------------------
# max_labware_top_z - drives GantryController's dynamic safe clearance height
# ---------------------------------------------------------------------------

def test_max_labware_top_z_zero_without_workspace():
    assert WorkspaceManager().max_labware_top_z() == 0.0


def test_max_labware_top_z_uses_origin_plus_plate_height(mgr):
    # Both plates share plate_type=96_well_standard and the same origin_z=15.0.
    assert mgr.max_labware_top_z() == pytest.approx(15.0 + _PLATE_HEIGHT_96)


def test_max_labware_top_z_picks_the_tallest_plate():
    m = WorkspaceManager()
    m.load_from_yaml(textwrap.dedent("""\
        name: mixed_bench
        calibration_reference_well: low/A1
        plates:
          - id: low
            plate_type: 24_well_standard
            origin: {x: 0.0, y: 0.0, z: 0.0}
          - id: tall
            plate_type: 100ml_beaker
            origin: {x: 150.0, y: 0.0, z: 0.0}
    """))
    from rxn_bench_gantry.plate_geometry import PlateGeometry
    tall_top = PlateGeometry.load("100ml_beaker").plate_height_mm
    assert m.max_labware_top_z() == pytest.approx(tall_top)
