"""Tests for _compute_bounds - the mm view-bounds logic behind the canvas's
"show more details" deck-boundary/corner-coordinate overlay.
"""
import importlib

import pytest

import rxn_bench_ui.devices as _devices

_devices.all_devices()
workspace_loader = importlib.import_module("rxn_bench_gantry_frontend.workspace_loader")

_compute_bounds = workspace_loader._compute_bounds

_PLATE_EXTENTS = [(10.0, 137.76, 20.0, 105.48)]
_LIMITS = (0.0, 350.0, 0.0, 350.0)


def test_no_plates_no_details_yields_zero_bounds():
    # Nothing loaded and the overlay is off - paintEvent's own gate keeps this
    # from ever being rendered, but the helper itself should stay well-defined.
    assert _compute_bounds([], None, show_details=False) == (0.0, 0.0, 0.0, 0.0)


def test_plates_only_fits_tightly_around_plates():
    min_x, max_x, min_y, max_y = _compute_bounds(_PLATE_EXTENTS, _LIMITS, show_details=False)
    assert min_x == pytest.approx(10.0 - 15.0)
    assert max_x == pytest.approx(137.76 + 15.0)
    assert min_y == pytest.approx(20.0 - 15.0)
    assert max_y == pytest.approx(105.48 + 15.0)


def test_details_with_no_plates_shows_deck_alone():
    bounds = _compute_bounds([], _LIMITS, show_details=True)
    assert bounds == _LIMITS


def test_details_with_plates_unions_deck_and_plate_bounds():
    # Padded plate extents dip slightly outside [0, 350] on two sides here
    # (10-15 and 20-15 go negative/near-zero) - the union takes whichever of
    # plate-or-deck bound is wider on each side.
    min_x, max_x, min_y, max_y = _compute_bounds(_PLATE_EXTENTS, _LIMITS, show_details=True)
    assert min_x == pytest.approx(10.0 - 15.0)   # padded plate extends past deck's x_min=0
    assert max_x == pytest.approx(350.0)         # deck's x_max extends past the padded plate
    assert min_y == pytest.approx(0.0)           # deck's y_min extends past the padded plate
    assert max_y == pytest.approx(350.0)         # deck's y_max extends past the padded plate


def test_details_unions_plate_overhang_beyond_deck_limits():
    # A plate positioned (or mis-measured) outside the nominal deck limits
    # must still be fully visible - the union takes the wider of the two.
    overhanging = [(-20.0, 137.76, 20.0, 400.0)]
    min_x, max_x, min_y, max_y = _compute_bounds(overhanging, _LIMITS, show_details=True)
    assert min_x == pytest.approx(-20.0 - 15.0)
    assert max_x == pytest.approx(350.0)
    assert min_y == pytest.approx(0.0)           # deck's y_min=0 extends past the padded plate's 5
    assert max_y == pytest.approx(400.0 + 15.0)


def test_details_without_limits_falls_back_to_plate_bounds():
    min_x, max_x, min_y, max_y = _compute_bounds(_PLATE_EXTENTS, None, show_details=True)
    assert min_x == pytest.approx(10.0 - 15.0)
    assert max_x == pytest.approx(137.76 + 15.0)
