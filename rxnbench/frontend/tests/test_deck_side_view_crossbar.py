"""X-gantry crossbar overlay in the side views (DeckSideViewCanvas).

The crossbar geometry (underside-above-tip, Y-thickness) arrives from the
server's extended GetLimits and is stored via set_limits; the overlay is only
drawn under "show more details". Both may be None (server has no crossbar model).
"""
import importlib

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

import rxn_bench_ui.devices as _devices
from rxn_bench_ui.themes import get as get_theme

_devices.all_devices()
workspace_loader = importlib.import_module("rxn_bench_gantry_frontend.workspace_loader")

_app = QApplication.instance() or QApplication([])
_THEME = get_theme("light")


def _canvas(axis: str):
    c = workspace_loader.DeckSideViewCanvas(_THEME, axis)
    c.resize(400, 300)
    return c


def test_set_limits_stores_crossbar_geometry():
    c = _canvas("x")
    c.set_limits(0.0, 350.0, 0.0, 350.0, 0.0, 340.0, 60.0, 90.0, 34.0)
    assert c._crossbar_clearance_above_tip == 90.0
    assert c._crossbar_y_thickness == 34.0


def test_set_limits_crossbar_defaults_to_none():
    c = _canvas("x")
    c.set_limits(0.0, 350.0, 0.0, 350.0, 0.0, 340.0, 60.0)  # no crossbar args
    assert c._crossbar_clearance_above_tip is None
    assert c._crossbar_y_thickness is None


def _render(axis: str, crossbar):
    c = _canvas(axis)
    c.load({"deck_height_mm": 0.0, "plates": [
        {"id": "p", "plate_type": "96_well_standard",
         "origin": {"x": 100.0, "y": 150.0, "z": 0.0}, "orientation": "standard"},
    ]})
    c.set_plate_specs({"96_well_standard": {
        "rows": 8, "columns": 12, "spacing_mm": 9.0, "well_diameter_mm": 6.94,
        "well_depth_mm": 36.0, "plate_height_mm": 39.0,
        "a1_offset_x": 14.38, "a1_offset_y": 11.24, "width_mm": 127.76, "height_mm": 85.48,
    }})
    ch, ct = crossbar if crossbar else (None, None)
    c.set_limits(0.0, 350.0, 0.0, 350.0, 0.0, 340.0, 60.0, ch, ct)
    c.set_current_position(100.0, 150.0, 20.0)
    c.set_show_details(True)
    img = QImage(c.size(), QImage.Format_ARGB32)
    img.fill(0)
    c.render(img)
    return img


def test_crossbar_overlay_actually_changes_the_rendered_side_view():
    # With the geometry set and show-details on, the crossbar overlay must
    # actually change the rendered pixels in both projections - i.e. it's wired
    # up and drawn, not silently dropped.
    for axis in ("x", "y"):
        assert _render(axis, crossbar=(90.0, 34.0)) != _render(axis, crossbar=None)
