"""Tests for plate_xy_extent and resolve_well_gxy - the pure geometry helpers
shared by the top-down WorkspaceCanvas and the new X/Z, Y/Z DeckSideViewCanvas.
"""
import importlib

import pytest

import rxn_bench_ui.devices as _devices

_devices.all_devices()
workspace_loader = importlib.import_module("rxn_bench_ui.devices.gantry.workspace_loader")

plate_xy_extent = workspace_loader.plate_xy_extent
resolve_well_gxy = workspace_loader.resolve_well_gxy

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
