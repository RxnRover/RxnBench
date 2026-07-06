"""Tests for WorkspaceManager: load, load_from_yaml, resolve_well, orientation."""
import textwrap
import pytest

from rxn_bench_gantry.workspace_manager import WorkspaceManager


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
    x, y, z = mgr.resolve_well("plates/A1")
    assert x == pytest.approx(50.0 + 14.38)
    assert y == pytest.approx(30.0 + 11.24)
    assert z == pytest.approx(15.0)


def test_a2_advances_x_by_spacing(mgr):
    x1, _, _ = mgr.resolve_well("plates/A1")
    x2, _, _ = mgr.resolve_well("plates/A2")
    assert x2 - x1 == pytest.approx(9.0)


def test_b1_advances_y_by_spacing(mgr):
    _, y1, _ = mgr.resolve_well("plates/A1")
    _, y2, _ = mgr.resolve_well("plates/B1")
    assert y2 - y1 == pytest.approx(9.0)


def test_rotated_a1_position(mgr):
    x, y, z = mgr.resolve_well("rotated/A1")
    assert x == pytest.approx(200.0 + (-11.24))
    assert y == pytest.approx(30.0  + 14.38)
    assert z == pytest.approx(15.0)


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
