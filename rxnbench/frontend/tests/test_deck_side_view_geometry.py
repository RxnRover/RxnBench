"""Tests for plate_xy_extent, resolve_well_gxy, and resolve_reference_plate_height -
the pure geometry helpers shared by the top-down WorkspaceCanvas, the X/Z, Y/Z
DeckSideViewCanvas, and the homing/toolhead-calibration dialogs' optional
non-contact Z-reference technique.
"""
import importlib
import textwrap

import pytest

import rxn_bench_ui.devices as _devices

_devices.all_devices()
workspace_loader = importlib.import_module("rxn_bench_ui.devices.gantry.workspace_loader")

plate_xy_extent = workspace_loader.plate_xy_extent
resolve_well_gxy = workspace_loader.resolve_well_gxy
resolve_reference_plate_height = workspace_loader.resolve_reference_plate_height

_SPEC = workspace_loader._PlateSpec(
    rows=8, cols=12, spacing_x=9.0, spacing_y=9.0, diam=6.94,
    a1x=14.38, a1y=11.24, width=127.76, height=85.48,
    plate_height_mm=39.0, well_depth_mm=36.0,
)


def test_plate_xy_extent_standard_orientation():
    plate = {"origin": {"x": 50.0, "y": 30.0}}
    x0, x1, y0, y1 = plate_xy_extent(plate, _SPEC)
    assert (x0, x1) == pytest.approx((50.0 - 63.88, 50.0 + 63.88))
    assert (y0, y1) == pytest.approx((30.0 - 42.74, 30.0 + 42.74))


def test_plate_xy_extent_rotated_swaps_half_dimensions():
    plate = {"origin": {"x": 50.0, "y": 30.0}, "orientation": "rotated_90"}
    x0, x1, y0, y1 = plate_xy_extent(plate, _SPEC)
    assert (x0, x1) == pytest.approx((50.0 - 42.74, 50.0 + 42.74))
    assert (y0, y1) == pytest.approx((30.0 - 63.88, 30.0 + 63.88))


def test_plate_xy_extent_defaults_missing_origin_to_zero():
    x0, x1, y0, y1 = plate_xy_extent({}, _SPEC)
    assert (x0, x1) == pytest.approx((-63.88, 63.88))
    assert (y0, y1) == pytest.approx((-42.74, 42.74))


def test_resolve_well_gxy_a1_standard():
    plate = {"origin": {"x": 50.0, "y": 30.0}}
    x, y = resolve_well_gxy(plate, _SPEC, "A1")
    assert x == pytest.approx(50.0 + 14.38 - 127.76 / 2)
    assert y == pytest.approx(30.0 + 11.24 - 85.48 / 2)


def test_resolve_well_gxy_advances_by_spacing():
    plate = {"origin": {"x": 50.0, "y": 30.0}}
    x1, y1 = resolve_well_gxy(plate, _SPEC, "A1")
    x2, _y2 = resolve_well_gxy(plate, _SPEC, "A2")
    _x3, y3 = resolve_well_gxy(plate, _SPEC, "B1")
    assert x2 - x1 == pytest.approx(9.0)
    assert y3 - y1 == pytest.approx(9.0)


def test_resolve_well_gxy_rotated_matches_backend_math():
    # Mirrors the backend's test_rotated_a1_position (same fixture numbers):
    # origin is the footprint centre; A1's offset from centre is rotated
    # -90 degrees (dx, dy) -> (-dy, dx) around that fixed pivot point.
    plate = {"origin": {"x": 200.0, "y": 30.0}, "orientation": "rotated_90"}
    centre_dx = 14.38 - 127.76 / 2
    centre_dy = 11.24 - 85.48 / 2
    x, y = resolve_well_gxy(plate, _SPEC, "A1")
    assert x == pytest.approx(200.0 + (-centre_dy))
    assert y == pytest.approx(30.0 + centre_dx)


def test_resolve_well_gxy_lowercase_label():
    plate = {"origin": {"x": 50.0, "y": 30.0}}
    upper = resolve_well_gxy(plate, _SPEC, "A1")
    lower = resolve_well_gxy(plate, _SPEC, "a1")
    assert lower == pytest.approx(upper)


def test_resolve_well_gxy_invalid_label_returns_none():
    plate = {"origin": {"x": 50.0, "y": 30.0}}
    assert resolve_well_gxy(plate, _SPEC, "not-a-well") is None
    assert resolve_well_gxy(plate, _SPEC, "") is None


# ---------------------------------------------------------------------------
# resolve_reference_plate_height
# ---------------------------------------------------------------------------

_WORKSPACE_YAML = textwrap.dedent("""\
    name: test_bench
    calibration_reference_well: plate1/A1
    plates:
      - id: plate1
        plate_type: 96_well_standard
        origin: {x: 100.0, y: 100.0, z: 15.0}
        orientation: standard
""")
_LABWARE = {"96_well_standard": {"plate_height_mm": 39.0}}


def test_resolve_reference_plate_height_happy_path():
    result = resolve_reference_plate_height(_WORKSPACE_YAML, _LABWARE)
    assert result == ("plate1", pytest.approx(15.0 + 39.0))


def test_resolve_reference_plate_height_no_workspace():
    assert resolve_reference_plate_height("", _LABWARE) is None


def test_resolve_reference_plate_height_no_reference_well_configured():
    yaml_text = textwrap.dedent("""\
        name: test_bench
        calibration_reference_well: ""
        plates:
          - id: plate1
            plate_type: 96_well_standard
            origin: {x: 100.0, y: 100.0, z: 15.0}
    """)
    assert resolve_reference_plate_height(yaml_text, _LABWARE) is None


def test_resolve_reference_plate_height_unknown_plate_id():
    yaml_text = textwrap.dedent("""\
        name: test_bench
        calibration_reference_well: nonexistent/A1
        plates:
          - id: plate1
            plate_type: 96_well_standard
            origin: {x: 100.0, y: 100.0, z: 15.0}
    """)
    assert resolve_reference_plate_height(yaml_text, _LABWARE) is None


def test_resolve_reference_plate_height_missing_plate_height_in_labware():
    assert resolve_reference_plate_height(_WORKSPACE_YAML, {"96_well_standard": {}}) is None
    assert resolve_reference_plate_height(_WORKSPACE_YAML, {}) is None


def test_resolve_reference_plate_height_defaults_missing_origin_z_to_zero():
    yaml_text = textwrap.dedent("""\
        name: test_bench
        calibration_reference_well: plate1/A1
        plates:
          - id: plate1
            plate_type: 96_well_standard
            origin: {x: 100.0, y: 100.0}
    """)
    result = resolve_reference_plate_height(yaml_text, _LABWARE)
    assert result == ("plate1", pytest.approx(39.0))


def test_resolve_reference_plate_height_malformed_yaml_returns_none():
    assert resolve_reference_plate_height("not: valid: yaml: [", _LABWARE) is None


def test_resolve_reference_plate_height_folds_in_deck_height():
    # With a shared deck, the reference top surface rides on top of it:
    # deck(8) + footprint origin.z(15) + plate_height(39).
    yaml_text = textwrap.dedent("""\
        name: test_bench
        calibration_reference_well: plate1/A1
        deck_height_mm: 8.0
        plates:
          - id: plate1
            plate_type: 96_well_standard
            origin: {x: 100.0, y: 100.0, z: 15.0}
    """)
    result = resolve_reference_plate_height(yaml_text, _LABWARE)
    assert result == ("plate1", pytest.approx(8.0 + 15.0 + 39.0))


def test_resolve_reference_plate_height_deck_defaults_to_zero():
    # _WORKSPACE_YAML has no deck_height_mm - must behave exactly as before.
    result = resolve_reference_plate_height(_WORKSPACE_YAML, _LABWARE)
    assert result == ("plate1", pytest.approx(15.0 + 39.0))
