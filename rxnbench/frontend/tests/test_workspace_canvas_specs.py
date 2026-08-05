"""Tests for the server-labware -> canvas plate-spec conversion.

Plate geometry is single-sourced from the backend's labware YAML (fetched over
the GetLabware RPC); the canvas must render exactly what the server serves.
"""
import importlib

import pytest

# Load the gantry device plugin package the same way the app does, so the
# module's relative imports resolve.
import rxn_bench_ui.devices as _devices

_devices.all_devices()
workspace_loader = importlib.import_module("rxn_bench_gantry_frontend.workspace_loader")


_SERVER_96_WELL = {
    "rows": 8,
    "columns": 12,
    "spacing_mm": 9.0,
    "well_diameter_mm": 6.94,
    "well_depth_mm": 10.67,
    "a1_offset_x": 14.38,
    "a1_offset_y": 11.24,
    "width_mm": 127.76,
    "height_mm": 85.48,
}


def test_plate_spec_from_labware_maps_all_fields():
    spec = workspace_loader.plate_spec_from_labware(_SERVER_96_WELL)
    assert spec.rows == 8 and spec.cols == 12
    assert spec.spacing_x == pytest.approx(9.0)
    assert spec.spacing_y == pytest.approx(9.0)
    assert spec.diam == pytest.approx(6.94)
    assert spec.a1x == pytest.approx(14.38)
    assert spec.a1y == pytest.approx(11.24)
    assert spec.width == pytest.approx(127.76)
    assert spec.height == pytest.approx(85.48)


def test_plate_spec_supports_asymmetric_spacing():
    data = {k: v for k, v in _SERVER_96_WELL.items() if k != "spacing_mm"}
    data["spacing_mm_x"] = 26.70
    data["spacing_mm_y"] = 32.20
    spec = workspace_loader.plate_spec_from_labware(data)
    assert spec.spacing_x == pytest.approx(26.70)
    assert spec.spacing_y == pytest.approx(32.20)


def test_plate_spec_missing_spacing_raises():
    data = {k: v for k, v in _SERVER_96_WELL.items() if k != "spacing_mm"}
    with pytest.raises(ValueError):
        workspace_loader.plate_spec_from_labware(data)


def test_plate_spec_falls_back_when_axis_keys_present_but_none():
    # dataclasses.asdict() (used by GetLabware) includes spacing_mm_x/y as
    # explicit None for plates that only set spacing_mm - .get() must not
    # mistake a present-but-None value for "key absent, use the default".
    data = {**_SERVER_96_WELL, "spacing_mm_x": None, "spacing_mm_y": None}
    spec = workspace_loader.plate_spec_from_labware(data)
    assert spec.spacing_x == pytest.approx(9.0)
    assert spec.spacing_y == pytest.approx(9.0)


def test_plate_spec_defaults_footprint_when_missing():
    data = {k: v for k, v in _SERVER_96_WELL.items() if k not in ("width_mm", "height_mm")}
    spec = workspace_loader.plate_spec_from_labware(data)
    assert spec.width == pytest.approx(127.76)
    assert spec.height == pytest.approx(85.48)


def test_missing_required_field_raises():
    data = {k: v for k, v in _SERVER_96_WELL.items() if k != "rows"}
    with pytest.raises(KeyError):
        workspace_loader.plate_spec_from_labware(data)


def test_plate_spec_maps_plate_height_when_present():
    data = {**_SERVER_96_WELL, "plate_height_mm": 39.0}
    spec = workspace_loader.plate_spec_from_labware(data)
    assert spec.plate_height_mm == pytest.approx(39.0)
    assert spec.well_depth_mm == pytest.approx(10.67)  # from _SERVER_96_WELL


def test_plate_spec_defaults_plate_height_when_missing():
    # _SERVER_96_WELL predates plate_height_mm - exercises the fallback path
    # a real (older) server response would hit.
    spec = workspace_loader.plate_spec_from_labware(_SERVER_96_WELL)
    assert spec.plate_height_mm == pytest.approx(workspace_loader._FALLBACK_SPEC.plate_height_mm)


def test_plate_spec_defaults_well_depth_when_missing():
    data = {k: v for k, v in _SERVER_96_WELL.items() if k != "well_depth_mm"}
    spec = workspace_loader.plate_spec_from_labware(data)
    assert spec.well_depth_mm == pytest.approx(workspace_loader._FALLBACK_SPEC.well_depth_mm)
