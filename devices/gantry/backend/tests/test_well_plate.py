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
    assert plate_96.well_depth_mm == pytest.approx(10.67)


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
