"""Tests for _corner_wells_for - resolving a plate's 4 corner wells for calibration."""
import importlib
import textwrap

import rxn_bench_ui.devices as _devices

_devices.all_devices()
_dialog = importlib.import_module("rxn_bench_ui.devices.gantry.toolhead_calibration_dialog")
_corner_wells_for = _dialog._corner_wells_for

_WORKSPACE_96_WELL = textwrap.dedent("""\
    name: test_bench
    calibration_reference_well: 96-well/H1
    plates:
      - id: 96-well
        plate_type: 96_well_standard
        origin: {x: 175, y: 175, z: 15.0}
        orientation: rotated_90
""")

_LABWARE_96_WELL = {
    "96_well_standard": {"rows": 8, "columns": 12},
}


def test_corner_h1_reference_yields_all_four_grid_corners():
    corners = _corner_wells_for(_WORKSPACE_96_WELL, _LABWARE_96_WELL)
    assert corners == ["96-well/H1", "96-well/H12", "96-well/A1", "96-well/A12"]


def test_corner_a1_reference_yields_all_four_grid_corners():
    workspace = _WORKSPACE_96_WELL.replace("96-well/H1", "96-well/A1")
    corners = _corner_wells_for(workspace, _LABWARE_96_WELL)
    assert corners == ["96-well/A1", "96-well/A12", "96-well/H1", "96-well/H12"]


def test_corner_middle_well_reference_still_produces_four_distinct_wells():
    # Not a true grid corner, but the reflection math still yields 4 wells -
    # useful as a plate-wide check even if the configured reference isn't a corner.
    workspace = _WORKSPACE_96_WELL.replace("96-well/H1", "96-well/D6")
    corners = _corner_wells_for(workspace, _LABWARE_96_WELL)
    assert corners == ["96-well/D6", "96-well/D7", "96-well/E6", "96-well/E7"]


def test_falls_back_to_single_well_when_labware_missing_rows_columns():
    corners = _corner_wells_for(_WORKSPACE_96_WELL, {"96_well_standard": {}})
    assert corners == ["96-well/H1"]


def test_falls_back_to_single_well_when_plate_type_unknown():
    corners = _corner_wells_for(_WORKSPACE_96_WELL, {})
    assert corners == ["96-well/H1"]


def test_returns_empty_when_no_reference_well_configured():
    workspace = textwrap.dedent("""\
        name: test_bench
        calibration_reference_well: ""
        plates: []
    """)
    assert _corner_wells_for(workspace, _LABWARE_96_WELL) == []


def test_returns_empty_for_blank_workspace():
    assert _corner_wells_for("", _LABWARE_96_WELL) == []


def test_malformed_well_label_falls_back_to_single_well():
    workspace = _WORKSPACE_96_WELL.replace("96-well/H1", "96-well/notawell")
    corners = _corner_wells_for(workspace, _LABWARE_96_WELL)
    assert corners == ["96-well/notawell"]
