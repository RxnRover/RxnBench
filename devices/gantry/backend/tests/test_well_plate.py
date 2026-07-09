"""Smoke tests for PlateGeometry coordinate math and label parsing."""
import pytest

from rxn_bench_gantry.plate_geometry import PlateGeometry


@pytest.fixture
def plate_96():
    return PlateGeometry.load("96_well_standard")


@pytest.fixture
def plate_24():
    return PlateGeometry.load("24_well_standard")


def test_list_available_includes_bundled():
    available = PlateGeometry.list_available()
    assert "96_well_standard" in available
    assert "24_well_standard" in available


def test_96_well_count(plate_96):
    assert plate_96.well_count == 96


def test_96_rows_cols(plate_96):
    assert plate_96.rows == 8
    assert plate_96.columns == 12


def test_96_spacing(plate_96):
    assert plate_96.spacing_mm == pytest.approx(9.0)


def test_96_well_depth(plate_96):
    # Depth is operator-tuned per bench (labware YAML is editable config),
    # so assert it is sane rather than pinning a catalogue value.
    assert plate_96.well_depth_mm > 0


def test_96_plate_height_covers_well_depth(plate_96):
    # The top surface a travel move must clear can't sit below the well's
    # own bottom, or the "safe" clearance height would be a lie.
    assert plate_96.plate_height_mm >= plate_96.well_depth_mm


def test_96_parse_a1(plate_96):
    assert plate_96.parse_label("A1") == (0, 0)


def test_96_parse_h12(plate_96):
    assert plate_96.parse_label("H12") == (7, 11)


def test_96_parse_d6(plate_96):
    assert plate_96.parse_label("D6") == (3, 5)


def test_96_parse_lowercase(plate_96):
    assert plate_96.parse_label("a1") == (0, 0)


def test_96_out_of_range_label(plate_96):
    with pytest.raises(ValueError):
        plate_96.parse_label("I1")


def test_96_out_of_range_column(plate_96):
    with pytest.raises(ValueError):
        plate_96.parse_label("A13")


def test_96_invalid_label_format(plate_96):
    with pytest.raises(ValueError):
        plate_96.parse_label("1A")


def test_96_a1_at_origin_offset(plate_96):
    x, y = plate_96.well_position("A1")
    assert x == pytest.approx(plate_96.a1_offset_x)
    assert y == pytest.approx(plate_96.a1_offset_y)


def test_96_a2_advances_by_spacing_in_x(plate_96):
    x0, _ = plate_96.well_position("A1")
    x1, _ = plate_96.well_position("A2")
    assert x1 - x0 == pytest.approx(plate_96.spacing_mm)


def test_96_b1_advances_by_spacing_in_y(plate_96):
    _, y0 = plate_96.well_position("A1")
    _, y1 = plate_96.well_position("B1")
    assert y1 - y0 == pytest.approx(plate_96.spacing_mm)


def test_96_h12_position(plate_96):
    x, y = plate_96.well_position("H12")
    assert x == pytest.approx(plate_96.a1_offset_x + 11 * plate_96.spacing_mm)
    assert y == pytest.approx(plate_96.a1_offset_y + 7  * plate_96.spacing_mm)


def test_24_well_count(plate_24):
    assert plate_24.well_count == 24


def test_24_rows_cols(plate_24):
    assert plate_24.rows == 4
    assert plate_24.columns == 6


def test_24_a1_position(plate_24):
    x, y = plate_24.well_position("A1")
    assert x == pytest.approx(plate_24.a1_offset_x)
    assert y == pytest.approx(plate_24.a1_offset_y)


def test_24_d6_position(plate_24):
    x, y = plate_24.well_position("D6")
    assert x == pytest.approx(plate_24.a1_offset_x + 5 * plate_24.spacing_mm)
    assert y == pytest.approx(plate_24.a1_offset_y + 3 * plate_24.spacing_mm)


def test_24_unknown_plate_raises():
    with pytest.raises(FileNotFoundError):
        PlateGeometry.load("does_not_exist_xyz")


# ---------------------------------------------------------------------------
# Malformed / half-written labware definitions
# ---------------------------------------------------------------------------

def _labware_dir(tmp_path, monkeypatch, files: dict[str, str]):
    import rxn_bench_gantry.plate_geometry as pg
    for name, content in files.items():
        (tmp_path / f"{name}.yaml").write_text(content)
    monkeypatch.setattr(pg, "_DEFINITIONS_DIR", tmp_path)


_GOOD_PLATE = """\
rows: 2
columns: 3
spacing_mm: 10.0
well_diameter_mm: 5.0
well_depth_mm: 8.0
plate_height_mm: 11.0
a1_offset_x: 12.0
a1_offset_y: 11.0
"""


def test_empty_definition_raises_clear_error(tmp_path, monkeypatch):
    """An empty labware file (the classic touch-then-forget) must say so,
    not crash with 'NoneType is not subscriptable'."""
    _labware_dir(tmp_path, monkeypatch, {"empty_plate": ""})
    with pytest.raises(ValueError, match="empty or not a YAML mapping"):
        PlateGeometry.load("empty_plate")


def test_missing_fields_named_in_error(tmp_path, monkeypatch):
    _labware_dir(tmp_path, monkeypatch, {"partial_plate": "rows: 2\ncolumns: 3\n"})
    with pytest.raises(ValueError, match="well_diameter_mm"):
        PlateGeometry.load("partial_plate")


def test_missing_spacing_named_in_error(tmp_path, monkeypatch):
    _labware_dir(tmp_path, monkeypatch, {"partial_plate": (
        "rows: 2\ncolumns: 3\nwell_diameter_mm: 1\nwell_depth_mm: 1\nplate_height_mm: 2\n"
        "a1_offset_x: 1\na1_offset_y: 1\n"
    )})
    with pytest.raises(ValueError, match="spacing_mm"):
        PlateGeometry.load("partial_plate")


def test_dump_all_yaml_skips_bad_definitions(tmp_path, monkeypatch, caplog):
    """One broken labware file must not take down GetLabware for every
    other plate type (deck canvas + get_workspace_wells depend on it)."""
    import yaml as _yaml
    _labware_dir(tmp_path, monkeypatch, {
        "good_plate": _GOOD_PLATE,
        "empty_plate": "",
    })
    with caplog.at_level("WARNING"):
        data = _yaml.safe_load(PlateGeometry.dump_all_yaml())
    assert "good_plate" in data
    assert "empty_plate" not in data
    assert any("empty_plate" in rec.message for rec in caplog.records)


def test_bundled_definitions_all_load():
    """Every labware file actually shipped in labware/ must be valid."""
    for name in PlateGeometry.list_available():
        geom = PlateGeometry.load(name)
        assert geom.well_count > 0
