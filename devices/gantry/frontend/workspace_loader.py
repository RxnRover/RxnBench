"""Workspace loader panel - imports workspace YAML and renders a to-scale 2-D deck view.

All server communication goes through the shared GantryConnection (see
connection.py); plate geometry is fetched from the backend's labware
definitions instead of being hardcoded here.
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from PySide6.QtCore import QFile, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from .connection import GantryConnection

_UI_DIR = Path(__file__).parent / "ui"


def _default_workspaces_dir() -> Path:
    """Where the "Import Workspace YAML" dialog opens to find example workspaces.

    Frozen build: the `Workspaces/` folder staged next to the executable by
    rxnbench/frontend/packaging/copy_workflows.py. Source checkout: this
    device's own workspace/definitions/ directly, so devs see the same
    examples without needing a build. These are starting templates to import
    and edit - not the live config the gantry backend loads by name.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "Workspaces"
    return Path(__file__).resolve().parent.parent / "backend" / "src" / "rxn_bench_gantry" / "workspace" / "definitions"


@dataclass(frozen=True)
class _PlateSpec:
    rows: int
    cols: int
    spacing_x: float     # mm, centre-to-centre along columns
    spacing_y: float     # mm, centre-to-centre along rows
    diam: float          # mm, well diameter
    a1x: float           # mm, A1 centre from plate corner X
    a1y: float           # mm, A1 centre from plate corner Y
    width: float         # mm, overall plate footprint
    height: float        # mm, overall plate footprint
    plate_height_mm: float = 14.0  # mm, deck to plate top surface (side views)
    well_depth_mm: float   = 10.67  # mm, plate top surface to well bottom (side views)


# Used only until the server's labware definitions arrive (or if the fetch
# fails): a standard SBS 96-well plate.
_FALLBACK_SPEC = _PlateSpec(
    rows=8, cols=12, spacing_x=9.0, spacing_y=9.0, diam=6.94,
    a1x=14.38, a1y=11.24, width=127.76, height=85.48,
)

_PALETTE = [
    "#3b82f6", "#10b981", "#f59e0b",
    "#8b5cf6", "#ef4444", "#06b6d4",
]


def effective_engage_depth(z_engage: float, well_depth_mm: float) -> float:
    """Blended engagement depth the backend actually descends to.

    Mirrors GantryController._effective_engage_depth so the side-view marker
    shows roughly where the tip really engages, not the toolhead's raw
    configured z_engage: the mean of z_engage and the well's own depth, capped
    at the well depth. The backend additionally holds the tip a small
    machine-configured margin above the well bottom (engage_bottom_margin_mm),
    which this marker does not model - it isn't sent to the frontend - so in the
    rare case where the blend reaches the bottom the marker sits a couple mm
    deeper than reality. Re-derived here rather than imported, like the rest of
    this module's geometry.
    """
    return min((z_engage + well_depth_mm) / 2, well_depth_mm)


def _compute_bounds(
    plate_extents: list[tuple[float, float, float, float]],
    limits: tuple[float, float, float, float] | None,
    show_details: bool,
    pad: float = 15.0,
) -> tuple[float, float, float, float]:
    """Compute the mm view bounds (min_x, max_x, min_y, max_y) for the canvas.

    Normally the view fits tightly around the loaded plates. When
    show_details is on and axis limits are known, the deck's full bed is
    folded into the bounds too (via union, so plates that overhang a
    mis-measured deck are still fully visible) - or used on its own when no
    plates are loaded yet, so the empty deck grid can still be previewed.

    Args:
        plate_extents: Each plate's (x0, x1, y0, y1) footprint in mm.
        limits: Deck axis limits as (x_min, x_max, y_min, y_max), or None if
            not yet known.
        show_details: Whether the "show more details" overlay is active.
        pad: Margin in mm added around plate-derived bounds.
    """
    if plate_extents:
        min_x = min(e[0] for e in plate_extents) - pad
        min_y = min(e[2] for e in plate_extents) - pad
        max_x = max(e[1] for e in plate_extents) + pad
        max_y = max(e[3] for e in plate_extents) + pad
    else:
        min_x = min_y = max_x = max_y = 0.0

    if show_details and limits is not None:
        lx_min, lx_max, ly_min, ly_max = limits
        if plate_extents:
            min_x, min_y = min(min_x, lx_min), min(min_y, ly_min)
            max_x, max_y = max(max_x, lx_max), max(max_y, ly_max)
        else:
            min_x, max_x, min_y, max_y = lx_min, lx_max, ly_min, ly_max

    return min_x, max_x, min_y, max_y


_WELL_LABEL_RE = re.compile(r'^([A-Za-z])(\d+)$')
_ROTATED_ORIENTATIONS = ("rotated_90", "rotated_270")


def _apply_orientation(dx: float, dy: float, orientation: str | None) -> tuple[float, float]:
    """Rotate plate-local (dx, dy) into gantry XY. Mirrors backend _apply_orientation."""
    if orientation == "rotated_90":
        return -dy, dx
    if orientation == "rotated_270":
        return dy, -dx
    return dx, dy


def plate_xy_extent(plate: dict, spec: _PlateSpec) -> tuple[float, float, float, float]:
    """Return a placed plate's (x0, x1, y0, y1) footprint extent in mm.

    Shared by the top-down canvas (its own bounds) and the side-view
    canvases (their horizontal-axis bounds), so both project the exact same
    footprint math.

    Args:
        plate: One entry from a workspace YAML's ``plates`` list.
        spec: That plate's geometry, as returned by plate_spec_from_labware.
    """
    # origin is the centre of the plate's footprint; rotation swaps which
    # footprint dimension is half-width vs half-height but the centre point
    # itself never moves.
    origin = plate.get("origin") or {}
    ox_ = origin.get("x") or 0.0
    oy_ = origin.get("y") or 0.0
    if plate.get("orientation") in _ROTATED_ORIENTATIONS:
        hw, hh = spec.height / 2, spec.width / 2
    else:
        hw, hh = spec.width / 2, spec.height / 2
    return ox_ - hw, ox_ + hw, oy_ - hh, oy_ + hh


def resolve_well_gxy(plate: dict, spec: _PlateSpec, well_label: str) -> tuple[float, float] | None:
    """Compute a well's absolute gantry (x, y) in mm from its plate placement + geometry.

    Mirrors WorkspaceManager.resolve_well's XY math client-side (rotation
    pivoting around the footprint centre, same as the per-well dot grid this
    canvas already draws), so a highlighted-well marker on the side-view
    canvases lands at the same spot the top-down canvas draws that well's dot.

    Args:
        plate: One entry from a workspace YAML's ``plates`` list.
        spec: That plate's geometry, as returned by plate_spec_from_labware.
        well_label: Well label, e.g. ``'A1'``.

    Returns:
        (x, y) in mm, or None if well_label doesn't parse as letter+number.
    """
    m = _WELL_LABEL_RE.match(well_label.strip())
    if not m:
        return None
    row = ord(m.group(1).upper()) - ord('A')
    col = int(m.group(2)) - 1
    origin = plate.get("origin") or {}
    ox_ = origin.get("x") or 0.0
    oy_ = origin.get("y") or 0.0
    pdx = spec.a1x + col * spec.spacing_x
    pdy = spec.a1y + row * spec.spacing_y
    cdx = pdx - spec.width / 2
    cdy = pdy - spec.height / 2
    gdx, gdy = _apply_orientation(cdx, cdy, plate.get("orientation"))
    return ox_ + gdx, oy_ + gdy


def resolve_reference_plate_height(workspace_yaml: str, labware: dict) -> tuple[str, float] | None:
    """Resolve the workspace's calibration_reference_well into (plate_id, top_surface_height_mm).

    Used by the homing and toolhead-calibration dialogs to offer a
    non-contact Z-reference technique: hover the tip at this known height
    (optionally with a paper shim) instead of touching the deck or a
    toolhead's tip touching it directly. Top surface height is
    ``deck_height_mm + origin_z + plate_height_mm`` - the same quantity
    WorkspaceManager.resolve_well() docks well-targeted moves at server-side
    (the shared deck/workplate height is folded in so this reference lands at
    the plate's real top even when the whole deck is raised off the bed).

    Args:
        workspace_yaml: Raw YAML of the active workspace (as returned by
            GetWorkspaceYaml), or "" if none is loaded.
        labware: ``{plate_type: geometry dict}`` as returned by fetch_labware().

    Returns:
        (plate_id, height_mm), or None if there's no workspace, no
        calibration_reference_well configured, or the referenced plate/type
        can't be resolved - callers should fall back to the original
        touch-the-deck approach (height 0) in that case.
    """
    if not workspace_yaml:
        return None
    try:
        data = yaml.safe_load(workspace_yaml) or {}
        ref_well = (data.get("calibration_reference_well") or "").strip()
        if not ref_well or "/" not in ref_well:
            return None
        plate_id, _well_label = (p.strip() for p in ref_well.split("/", 1))
        plates = data.get("plates", []) or []
        plate = next((p for p in plates if p.get("id") == plate_id), None)
        if plate is None:
            return None
        geom = labware.get(plate.get("plate_type")) or {}
        plate_height_mm = geom.get("plate_height_mm")
        if plate_height_mm is None:
            return None
        origin_z = (plate.get("origin") or {}).get("z") or 0.0
        deck_height_mm = data.get("deck_height_mm") or 0.0
        return plate_id, float(deck_height_mm) + origin_z + float(plate_height_mm)
    except Exception:
        return None


def plate_spec_from_labware(data: dict) -> _PlateSpec:
    """Convert one server-side labware geometry dict into a canvas _PlateSpec.

    Args:
        data: Geometry dict as served by the gantry's GetLabware command
            (rows, columns, spacing_mm or spacing_mm_x/spacing_mm_y,
            well_diameter_mm, a1_offset_x/y, width_mm, height_mm).
    """
    spacing = data.get("spacing_mm")
    spacing_x = data.get("spacing_mm_x") if data.get("spacing_mm_x") is not None else spacing
    spacing_y = data.get("spacing_mm_y") if data.get("spacing_mm_y") is not None else spacing
    if spacing_x is None or spacing_y is None:
        raise ValueError("labware entry missing spacing_mm or spacing_mm_x/spacing_mm_y")
    return _PlateSpec(
        rows=int(data["rows"]),
        cols=int(data["columns"]),
        spacing_x=float(spacing_x),
        spacing_y=float(spacing_y),
        diam=float(data["well_diameter_mm"]),
        a1x=float(data["a1_offset_x"]),
        a1y=float(data["a1_offset_y"]),
        width=float(data.get("width_mm", _FALLBACK_SPEC.width)),
        height=float(data.get("height_mm", _FALLBACK_SPEC.height)),
        plate_height_mm=float(data.get("plate_height_mm", _FALLBACK_SPEC.plate_height_mm)),
        well_depth_mm=float(data.get("well_depth_mm", _FALLBACK_SPEC.well_depth_mm)),
    )


class WorkspaceCanvas(QWidget):
    """Renders a to-scale top-down view of a workspace YAML definition."""

    def __init__(self, t: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t           = t
        self._plates: list[dict] = []
        self._plate_specs: dict[str, _PlateSpec] = {}
        self._cal_ref     = ""
        self._active_well = ("", "")   # (plate_id, well_label) to highlight
        self._current_pos: tuple[float, float] | None = None  # gantry XY mm
        self._limits: tuple[float, float, float, float] | None = None  # x_min, x_max, y_min, y_max
        self._show_details = False
        self.setMinimumSize(300, 200)

    def set_plate_specs(self, labware: dict) -> None:
        """Install server-sourced plate geometries and repaint.

        Args:
            labware: Dict mapping plate type name to its geometry dict, as
                returned by GantryConnection.fetch_labware().
        """
        specs: dict[str, _PlateSpec] = {}
        for name, data in labware.items():
            try:
                specs[name] = plate_spec_from_labware(data)
            except (KeyError, TypeError, ValueError):
                continue  # skip malformed entries, keep the rest
        self._plate_specs = specs
        self.update()

    def load(self, workspace: dict) -> None:
        """Parse a workspace dict and repaint the canvas.

        Args:
            workspace: Parsed workspace YAML dict containing a ``plates`` list.
        """
        self._plates  = workspace.get("plates", [])
        self._cal_ref = workspace.get("calibration_reference_well", "")
        self.update()

    def clear(self) -> None:
        """Remove all plates and reset the active-well and position overlays."""
        self._plates  = []
        self._cal_ref = ""
        self._active_well = ("", "")
        self._current_pos = None
        self.update()

    def set_active_well(self, plate_id: str, well_label: str) -> None:
        """Highlight the given well on the canvas.

        Args:
            plate_id: Plate identifier as defined in the workspace YAML.
            well_label: Well label such as ``"A1"``.
        """
        self._active_well = (plate_id, well_label)
        self.update()

    def set_current_position(self, x: float, y: float) -> None:
        """Update the crosshair overlay to the gantry's current XY position in mm."""
        self._current_pos = (x, y)
        self.update()

    def set_limits(
        self,
        x_min: float, x_max: float, y_min: float, y_max: float,
        z_min: float = 0.0, z_max: float = 0.0,
    ) -> None:
        """Store the deck's axis limits and repaint.

        Args:
            x_min, x_max, y_min, y_max: Axis limits in mm, as reported by the
                server's GetLimits command.
            z_min, z_max: Accepted but unused - only X/Y are drawn on this
                2-D canvas. Kept so callers (DeckViewPanel) can pass the same
                6 positional args they'd give any other WorkspaceCanvas.
        """
        self._limits = (x_min, x_max, y_min, y_max)
        self.update()

    def set_show_details(self, show: bool) -> None:
        """Toggle the deck-boundary/corner-coordinate overlay and repaint."""
        self._show_details = show
        self.update()

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and repaint the canvas."""
        self._t = t
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(), QColor(self._t["bg_surface"]))
            if not self._plates and not (self._show_details and self._limits):
                p.setPen(QColor(self._t["text_dim"]))
                p.setFont(QFont("sans-serif", 11))
                p.drawText(self.rect(), Qt.AlignCenter, "No workspace loaded.")
            else:
                # Live-editing may briefly produce syntactically valid but
                # semantically incomplete YAML (e.g. a plate with no origin
                # yet); skip this frame rather than crash the whole app.
                try:
                    self._paint_workspace(p)
                except (TypeError, KeyError, ValueError, AttributeError, ZeroDivisionError):
                    pass
        finally:
            p.end()

    def _paint_workspace(self, p: QPainter) -> None:
        t   = self._t
        W   = self.width()
        H   = self.height()
        PAD = 40  # px around the content

        # Gather plate specs and bounding box (in mm)
        entries: list[tuple[dict, _PlateSpec]] = []
        for plate in self._plates:
            spec = self._plate_specs.get(plate.get("plate_type", ""), _FALLBACK_SPEC)
            entries.append((plate, spec))

        extents = [plate_xy_extent(pl, sp) for pl, sp in entries]
        min_x, max_x, min_y, max_y = _compute_bounds(extents, self._limits, self._show_details)

        span_x = max_x - min_x or 1
        span_y = max_y - min_y or 1

        avail_w = W - 2 * PAD
        avail_h = H - 2 * PAD
        scale   = min(avail_w / span_x, avail_h / span_y)   # px / mm

        rend_w  = span_x * scale
        rend_h  = span_y * scale
        ox_off  = PAD + (avail_w - rend_w) / 2
        oy_off  = PAD + (avail_h - rend_h) / 2

        def to_px(mmx: float, mmy: float) -> tuple[float, float]:
            # Y flipped so Y=min_y is at screen-bottom (conventional lab view)
            return (
                ox_off + (mmx - min_x) * scale,
                oy_off + rend_h - (mmy - min_y) * scale,
            )

        # Parse cal ref
        cal_plate_id, cal_well = "", ""
        if "/" in self._cal_ref:
            cal_plate_id, cal_well = self._cal_ref.split("/", 1)

        for i, (plate, spec) in enumerate(entries):
            pid         = plate.get("id", f"plate{i + 1}")
            origin      = plate.get("origin") or {}
            ox          = origin.get("x") or 0.0
            oy          = origin.get("y") or 0.0
            orientation = plate.get("orientation")
            rotated     = orientation in _ROTATED_ORIENTATIONS
            color       = QColor(_PALETTE[i % len(_PALETTE)])

            def _well_gxy(pdx: float, pdy: float) -> tuple[float, float]:
                # Transform plate-local (pdx, pdy) to gantry XY, matching backend
                # _apply_orientation: origin is the footprint centre, so local
                # coords are re-centred before rotating around it.
                cdx = pdx - spec.width / 2
                cdy = pdy - spec.height / 2
                gdx, gdy = _apply_orientation(cdx, cdy, orientation)
                return ox + gdx, oy + gdy

            # Plate rectangle corners
            if rotated:
                hw, hh = spec.height / 2, spec.width / 2
            else:
                hw, hh = spec.width / 2, spec.height / 2
            sx1, sy1 = to_px(ox - hw, oy + hh)
            sx2, sy2 = to_px(ox + hw, oy - hh)
            rect = QRectF(sx1, sy1, sx2 - sx1, sy2 - sy1)

            fill = QColor(color); fill.setAlphaF(0.12)
            p.fillRect(rect, fill)
            p.setPen(QPen(color, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, 3, 3)

            # Wells
            r_px = max(1.5, (spec.diam / 2) * scale)
            draw_wells = spec.rows * spec.cols <= 384

            for row in range(spec.rows):
                rl = chr(ord("A") + row)
                for col in range(spec.cols):
                    wlabel = f"{rl}{col + 1}"
                    gx, gy = _well_gxy(
                        spec.a1x + col * spec.spacing_x,
                        spec.a1y + row * spec.spacing_y,
                    )
                    wx, wy = to_px(gx, gy)
                    is_cal = (pid == cal_plate_id and wlabel == cal_well)

                    is_active = (
                        pid == self._active_well[0]
                        and wlabel == self._active_well[1]
                    )
                    if is_cal:
                        ac = QColor(t["accent"])
                        p.setBrush(QBrush(ac))
                        p.setPen(QPen(ac.darker(130), 1.5))
                        wr = r_px * 1.6
                    elif is_active:
                        ac = QColor(t.get("dot_ok", "#22c55e"))
                        p.setBrush(QBrush(ac))
                        p.setPen(QPen(ac.darker(130), 1.5))
                        wr = r_px * 1.6
                    elif draw_wells:
                        wf = QColor(color); wf.setAlphaF(0.35)
                        p.setBrush(QBrush(wf))
                        p.setPen(QPen(color, 0.8))
                        wr = r_px
                    else:
                        continue

                    p.drawEllipse(QRectF(wx - wr, wy - wr, wr * 2, wr * 2))

            # A1 label
            a1gx, a1gy = _well_gxy(spec.a1x, spec.a1y)
            a1x_px, a1y_px = to_px(a1gx, a1gy)
            a1_fsz = max(6, min(12, int(scale * 3.5)))
            p.setPen(QColor(t["text"]))
            p.setFont(QFont("sans-serif", a1_fsz))
            p.drawText(
                QRectF(a1x_px + r_px + 2, a1y_px - a1_fsz, 60, a1_fsz * 2 + 4),
                Qt.AlignLeft | Qt.AlignVCenter,
                "A1",
            )

            # Plate ID label - skip when the plate rectangle is too small to fit text
            pid_fsz = max(7, min(14, int(scale * 4.5)))
            label_w = rect.width() - 10
            if label_w > 5:
                p.setPen(QColor(t["text"]))
                p.setFont(QFont("sans-serif", pid_fsz, QFont.Bold))
                p.drawText(
                    QRectF(sx1 + 5, sy1 + 4, label_w, max(pid_fsz + 4, 18)),
                    Qt.AlignLeft,
                    pid,
                )

        # Deck boundary + corner coordinates ("show more details" overlay)
        if self._show_details and self._limits:
            self._draw_deck_boundary(p, to_px, *self._limits, t)

        # Current gantry position crosshair
        if self._current_pos is not None:
            cx, cy = to_px(self._current_pos[0], self._current_pos[1])
            arm = 10
            cross_col = QColor(t.get("dot_warn", "#f59e0b"))
            p.setPen(QPen(cross_col, 2.0))
            p.drawLine(int(cx - arm), int(cy), int(cx + arm), int(cy))
            p.drawLine(int(cx), int(cy - arm), int(cx), int(cy + arm))
            p.setBrush(QBrush(cross_col))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(cx - 3, cy - 3, 6, 6))

        # Calibration reference label (bottom strip)
        if self._cal_ref:
            p.setPen(QColor(t["text_muted"]))
            p.setFont(QFont("sans-serif", 8))
            p.drawText(
                self.rect().adjusted(PAD, 0, -PAD, -6),
                Qt.AlignBottom | Qt.AlignLeft,
                f"▲ cal ref: {self._cal_ref}",
            )

        # Axis indicator (bottom-left)
        self._draw_axes(p, ox_off + 8, oy_off + rend_h - 8, t)

        # Scale bar (bottom-right)
        self._draw_scale_bar(p, scale, ox_off + rend_w, oy_off + rend_h, t)

    @staticmethod
    def _draw_axes(p: QPainter, ax: float, ay: float, t: dict) -> None:
        arm = 22
        col = QColor(t["text_dim"])
        p.setPen(QPen(col, 1.2))
        # X arrow
        p.drawLine(int(ax), int(ay), int(ax + arm), int(ay))
        p.drawLine(int(ax + arm), int(ay), int(ax + arm - 5), int(ay - 3))
        p.drawLine(int(ax + arm), int(ay), int(ax + arm - 5), int(ay + 3))
        # Y arrow (upward = positive Y in gantry)
        p.drawLine(int(ax), int(ay), int(ax), int(ay - arm))
        p.drawLine(int(ax), int(ay - arm), int(ax - 3), int(ay - arm + 5))
        p.drawLine(int(ax), int(ay - arm), int(ax + 3), int(ay - arm + 5))
        p.setFont(QFont("sans-serif", 7))
        p.setPen(col)
        p.drawText(QRectF(ax + arm + 2, ay - 6, 12, 12), "X")
        p.drawText(QRectF(ax - 8, ay - arm - 10, 12, 12), "Y")

    @staticmethod
    def _draw_deck_boundary(
        p: QPainter, to_px, x_min: float, x_max: float, y_min: float, y_max: float, t: dict,
    ) -> None:
        col = QColor(t.get("accent", "#3b82f6"))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, 1.5, Qt.DashLine))
        sx1, sy1 = to_px(x_min, y_max)  # screen top-left
        sx2, sy2 = to_px(x_max, y_min)  # screen bottom-right
        p.drawRect(QRectF(sx1, sy1, sx2 - sx1, sy2 - sy1))

        label_w, label_h = 90, 16
        p.setFont(QFont("sans-serif", 8, QFont.Bold))
        # Each corner's label is anchored just inside the boundary (toward
        # the rectangle's centre) so it stays on-canvas regardless of which
        # of the 4 corners it is, even when the deck fills nearly the whole
        # widget.
        corners = [
            (x_min, y_min, sx1, sy2, +1, -1),  # bottom-left: inward = right, up
            (x_max, y_min, sx2, sy2, -1, -1),  # bottom-right: inward = left, up
            (x_min, y_max, sx1, sy1, +1, +1),  # top-left: inward = right, down
            (x_max, y_max, sx2, sy1, -1, +1),  # top-right: inward = left, down
        ]
        for mx, my, px_, py_, sdx, sdy in corners:
            p.setBrush(QBrush(col))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(px_ - 3, py_ - 3, 6, 6))

            bx = px_ + (4 if sdx > 0 else -4 - label_w)
            by = py_ + (4 if sdy > 0 else -4 - label_h)
            align = Qt.AlignLeft if sdx > 0 else Qt.AlignRight
            p.setPen(QColor(t["text_muted"]))
            p.drawText(QRectF(bx, by, label_w, label_h), Qt.AlignVCenter | align, f"({mx:.0f}, {my:.0f})")

    @staticmethod
    def _draw_scale_bar(p: QPainter, scale: float, rx: float, ry: float, t: dict) -> None:
        target_px = 70
        raw_mm    = target_px / scale
        magnitude = 10 ** math.floor(math.log10(max(raw_mm, 1e-9)))
        bar_mm    = next(
            (magnitude * f for f in (1, 2, 5, 10) if magnitude * f * scale >= target_px),
            magnitude * 10,
        )
        bar_px = bar_mm * scale
        bx0, bx1 = rx - bar_px, rx
        by        = ry + 16

        col = QColor(t["text_muted"])
        p.setPen(QPen(col, 1.5))
        p.drawLine(int(bx0), int(by), int(bx1), int(by))
        for bx in (bx0, bx1):
            p.drawLine(int(bx), int(by - 3), int(bx), int(by + 3))

        p.setPen(QColor(t["text_dim"]))
        p.setFont(QFont("sans-serif", 8))
        p.drawText(
            QRectF(bx0, by + 5, bar_px, 14), Qt.AlignCenter,
            f"{bar_mm:.0f} mm",
        )


class DeckSideViewCanvas(QWidget):
    """Renders a to-scale X/Z or Y/Z side elevation of a workspace.

    Shows what the top-down WorkspaceCanvas cannot: each plate's height
    above the deck, its well depth, the server's current safe clearance
    (travel) height, and - for the active well, if known - the toolhead's
    configured engagement depth. Fed the same plate/limits/position data as
    WorkspaceCanvas; see DeckViewPanel, which owns one of each and keeps
    them all current regardless of which is currently visible.
    """

    def __init__(self, t: dict, axis: str, parent: QWidget | None = None) -> None:
        """
        Args:
            t: Theme dict.
            axis: ``'x'`` for an X/Z side view, ``'y'`` for a Y/Z side view -
                selects which horizontal axis of the workspace is projected.
        """
        super().__init__(parent)
        self._t     = t
        self._axis  = axis
        self._plates: list[dict] = []
        self._deck_height_mm = 0.0   # shared deck/workplate top height above Z=0
        self._crossbar_clearance_above_tip: float | None = None  # X-gantry crossbar underside above tip
        self._crossbar_y_thickness: float | None = None
        self._plate_specs: dict[str, _PlateSpec] = {}
        self._active_well = ("", "")
        self._current_pos: tuple[float, float, float] | None = None  # gantry x, y, z mm
        # x_min, x_max, y_min, y_max, z_min, z_max, safe_clearance_z
        self._limits: tuple[float, float, float, float, float, float, float] | None = None
        self._toolhead_z_engage: float | None = None
        self._show_details = False
        self.setMinimumSize(300, 200)

    def set_plate_specs(self, labware: dict) -> None:
        specs: dict[str, _PlateSpec] = {}
        for name, data in labware.items():
            try:
                specs[name] = plate_spec_from_labware(data)
            except (KeyError, TypeError, ValueError):
                continue
        self._plate_specs = specs
        self.update()

    def load(self, workspace: dict) -> None:
        self._plates = workspace.get("plates", [])
        self._deck_height_mm = float(workspace.get("deck_height_mm") or 0.0)
        self.update()

    def clear(self) -> None:
        self._plates = []
        self._deck_height_mm = 0.0
        self._active_well = ("", "")
        self._current_pos = None
        self.update()

    def set_active_well(self, plate_id: str, well_label: str) -> None:
        self._active_well = (plate_id, well_label)
        self.update()

    def set_current_position(self, x: float, y: float, z: float) -> None:
        self._current_pos = (x, y, z)
        self.update()

    def set_limits(
        self,
        x_min: float, x_max: float, y_min: float, y_max: float,
        z_min: float, z_max: float, safe_clearance_z: float,
        crossbar_clearance_above_tip: float | None = None,
        crossbar_y_thickness: float | None = None,
    ) -> None:
        self._limits = (x_min, x_max, y_min, y_max, z_min, z_max, safe_clearance_z)
        self._crossbar_clearance_above_tip = crossbar_clearance_above_tip
        self._crossbar_y_thickness = crossbar_y_thickness
        self.update()

    def set_toolhead_z_engage(self, value: float | None) -> None:
        """Set the active toolhead's engagement depth, or None if no toolhead is active."""
        self._toolhead_z_engage = value
        self.update()

    def set_show_details(self, show: bool) -> None:
        """Toggle including the full deck axis extent in the horizontal bounds.

        Same idea as WorkspaceCanvas.set_show_details: off by default so the
        view fits tightly around the loaded plates, matching the top-down
        canvas's default look exactly.
        """
        self._show_details = show
        self.update()

    def set_theme(self, t: dict) -> None:
        self._t = t
        self.update()

    def _h_extent(self, plate: dict, spec: _PlateSpec) -> tuple[float, float]:
        x0, x1, y0, y1 = plate_xy_extent(plate, spec)
        return (x0, x1) if self._axis == "x" else (y0, y1)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing)
            p.fillRect(self.rect(), QColor(self._t["bg_surface"]))
            if not self._plates and self._limits is None:
                p.setPen(QColor(self._t["text_dim"]))
                p.setFont(QFont("sans-serif", 11))
                p.drawText(self.rect(), Qt.AlignCenter, "No workspace loaded.")
            else:
                try:
                    self._paint_side(p)
                except (TypeError, KeyError, ValueError, AttributeError, ZeroDivisionError):
                    pass
        finally:
            p.end()

    def _paint_side(self, p: QPainter) -> None:
        t   = self._t
        W   = self.width()
        H   = self.height()
        PAD = 40
        pad_mm = 15.0

        entries: list[tuple[dict, _PlateSpec]] = [
            (plate, self._plate_specs.get(plate.get("plate_type", ""), _FALLBACK_SPEC))
            for plate in self._plates
        ]
        deck = self._deck_height_mm
        h_spans = [self._h_extent(pl, sp) for pl, sp in entries]
        plate_tops = [
            deck + ((plate.get("origin") or {}).get("z", 0.0)) + sp.plate_height_mm
            for plate, sp in entries
        ]

        x_min = x_max = y_min = y_max = z_min = z_max = safe_z = None
        if self._limits is not None:
            x_min, x_max, y_min, y_max, z_min, z_max, safe_z = self._limits
        axis_limit = (x_min, x_max) if self._axis == "x" else (y_min, y_max)

        # Tight-fit to the loaded plates by default - same as the top-down
        # canvas's _compute_bounds - and only union in the full deck extent
        # when show_details is on. Unconditionally including the whole deck
        # (hundreds of mm) around a handful of plates clustered in one corner
        # was the actual cause of most of the wasted canvas space; no amount
        # of scale-formula tweaking fixes bounds that are needlessly wide.
        if h_spans:
            hmin = min(s[0] for s in h_spans) - pad_mm
            hmax = max(s[1] for s in h_spans) + pad_mm
        else:
            hmin = hmax = 0.0
        if self._show_details and axis_limit[0] is not None:
            if h_spans:
                hmin, hmax = min(hmin, axis_limit[0]), max(hmax, axis_limit[1])
            else:
                hmin, hmax = axis_limit

        # z_max (the machine's hard travel ceiling, e.g. 340mm) is deliberately
        # excluded here - it dwarfs any real plate height or safe-travel value
        # (typically well under 150mm), so including it turned most of the
        # canvas into dead space above the one line anyone actually cares
        # about. Fit tightly to the real content instead, same as the top
        # view fits tightly to plates by default.
        current_z = self._current_pos[2] if self._current_pos is not None else None
        z_lo = z_min if z_min is not None else 0.0
        z_hi_candidates = [z for z in (safe_z, current_z, *plate_tops) if z is not None]
        # Fold the crossbar underside into the vertical fit when it will be
        # drawn (show-details + geometry known + a current position): it rides
        # well above the tip, so without this the bar (and its label) sit jammed
        # against the very top edge of the auto-fitted view.
        if self._show_details and self._crossbar_clearance_above_tip is not None and current_z is not None:
            z_hi_candidates.append(current_z + self._crossbar_clearance_above_tip)
        z_hi = (max(z_hi_candidates) if z_hi_candidates else 50.0) + pad_mm

        span_h = hmax - hmin or 1
        span_z = z_hi - z_lo or 1
        avail_w = W - 2 * PAD
        avail_h = H - 2 * PAD
        # Exact same technique as the top-down canvas: one shared,
        # aspect-preserving scale. Tight bounds (above) are what actually
        # make this fill the canvas well, not a fancier scale formula.
        scale = min(avail_w / span_h, avail_h / span_z)

        rend_w = span_h * scale
        rend_h = span_z * scale
        ox_off = PAD + (avail_w - rend_w) / 2
        oy_off = PAD + (avail_h - rend_h) / 2

        def to_px(h_mm: float, z_mm: float) -> tuple[float, float]:
            return (
                ox_off + (h_mm - hmin) * scale,
                oy_off + rend_h - (z_mm - z_lo) * scale,
            )

        # Z=0 floor (the bed / machine origin)
        floor_col = QColor(t["text_dim"])
        p.setPen(QPen(floor_col, 1.5))
        fx0, fy0 = to_px(hmin, 0.0)
        fx1, _fy1 = to_px(hmax, 0.0)
        p.drawLine(int(fx0), int(fy0), int(fx1), int(fy0))
        p.setFont(QFont("sans-serif", 8))
        p.drawText(QRectF(fx0, fy0 - 16, 140, 14), Qt.AlignLeft, "Z=0 (bed)")

        # Shared deck/workplate top, when it's raised off the bed - plates ride on this
        if deck > 0:
            p.setPen(QPen(floor_col, 1.2, Qt.DotLine))
            dx0, dy0 = to_px(hmin, deck)
            dx1, _dy1 = to_px(hmax, deck)
            p.drawLine(int(dx0), int(dy0), int(dx1), int(dy0))
            p.drawText(QRectF(dx0, dy0 - 16, 160, 14), Qt.AlignLeft, f"deck top: {deck:.1f} mm")

        # Safe clearance-travel height
        if safe_z is not None:
            col = QColor(t.get("accent", "#3b82f6"))
            p.setPen(QPen(col, 1.5, Qt.DashLine))
            sx0, sy0 = to_px(hmin, safe_z)
            sx1, _sy1 = to_px(hmax, safe_z)
            p.drawLine(int(sx0), int(sy0), int(sx1), int(sy0))
            p.setPen(col)
            p.drawText(
                QRectF(sx1 - 170, sy0 - 16, 170, 14), Qt.AlignRight,
                f"safe travel: {safe_z:.1f} mm",
            )

        # X-gantry crossbar (show-details only): its underside rides
        # crossbar_clearance_above_tip above the *current* tip Z, so it can hit
        # a taller plate in its Y-row when the gantry descends. Draw where it
        # currently sits so the operator can see the collision envelope.
        H = self._crossbar_clearance_above_tip
        if self._show_details and H is not None and self._current_pos is not None:
            bar_z = self._current_pos[2] + H
            bar_col = QColor(t.get("warning", "#f59e0b"))
            p.setPen(QPen(bar_col, 2.0))
            if self._axis == "x":
                # bar spans the full X travel at this height
                bx0, by = to_px(hmin, bar_z)
                bx1, _ = to_px(hmax, bar_z)
            else:
                # y/z view: the bar shows as its Y-thickness band at the carriage Y
                ty = self._crossbar_y_thickness or 0.0
                cy = self._current_pos[1]
                bx0, by = to_px(cy - ty / 2, bar_z)
                bx1, _ = to_px(cy + ty / 2, bar_z)
            p.drawLine(int(bx0), int(by), int(bx1), int(by))
            p.setPen(bar_col)
            p.drawText(QRectF(bx0, by - 16, 150, 14), Qt.AlignLeft, "X-gantry bar")

        cal_plate_id, cal_well = self._active_well

        for i, ((plate, spec), (h0, h1)) in enumerate(zip(entries, h_spans)):
            pid    = plate.get("id", f"plate{i + 1}")
            # The plate rests on the shared deck, so its resting surface is
            # deck_height + its own footprint offset (origin.z) above Z=0.
            rest_z = deck + ((plate.get("origin") or {}).get("z") or 0.0)
            top_z  = rest_z + spec.plate_height_mm
            bottom_z = top_z - spec.well_depth_mm
            color  = QColor(_PALETTE[i % len(_PALETTE)])

            px0, py0 = to_px(h0, top_z)
            px1, py1 = to_px(h1, rest_z)
            rect = QRectF(px0, py0, px1 - px0, py1 - py0)
            fill = QColor(color); fill.setAlphaF(0.15)
            p.fillRect(rect, fill)
            p.setPen(QPen(color, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(rect)

            # Well-bottom line, within this plate's own footprint
            wb_x0, wb_y = to_px(h0, bottom_z)
            wb_x1, _ = to_px(h1, bottom_z)
            p.setPen(QPen(color.darker(120), 1.2, Qt.DashLine))
            p.drawLine(int(wb_x0), int(wb_y), int(wb_x1), int(wb_y))

            label_w = rect.width() - 8
            if label_w > 5:
                p.setPen(QColor(t["text"]))
                p.setFont(QFont("sans-serif", 8, QFont.Bold))
                p.drawText(QRectF(px0 + 4, py0 + 2, label_w, 14), Qt.AlignLeft, pid)

            # Active-well guide: precise horizontal position + engagement depth
            if pid == cal_plate_id:
                gxy = resolve_well_gxy(plate, spec, cal_well)
                if gxy is not None:
                    h_pos = gxy[0] if self._axis == "x" else gxy[1]
                    ac = QColor(t.get("dot_ok", "#22c55e"))
                    p.setPen(QPen(ac, 1.5, Qt.DashLine))
                    gx0, gy0 = to_px(h_pos, top_z)
                    _gx1, gy1 = to_px(h_pos, bottom_z)
                    p.drawLine(int(gx0), int(gy0), int(gx0), int(gy1))
                    if self._toolhead_z_engage is not None:
                        eff = effective_engage_depth(
                            self._toolhead_z_engage, spec.well_depth_mm
                        )
                        engage_z = top_z - eff
                        ex, ey = to_px(h_pos, engage_z)
                        p.setPen(QPen(ac, 2.0))
                        p.drawLine(int(ex - 6), int(ey), int(ex + 6), int(ey))
                        p.setFont(QFont("sans-serif", 8))
                        p.drawText(
                            QRectF(ex + 8, ey - 7, 120, 14), Qt.AlignLeft,
                            f"engage {eff:.1f} mm",
                        )

        # Current gantry position marker
        if self._current_pos is not None:
            gx, gy, gz = self._current_pos
            h_pos = gx if self._axis == "x" else gy
            cx, cy = to_px(h_pos, gz)
            arm = 10
            cross_col = QColor(t.get("dot_warn", "#f59e0b"))
            p.setPen(QPen(cross_col, 2.0))
            p.drawLine(int(cx - arm), int(cy), int(cx + arm), int(cy))
            p.drawLine(int(cx), int(cy - arm), int(cx), int(cy + arm))
            p.setBrush(QBrush(cross_col))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(cx - 3, cy - 3, 6, 6))

        # Axis labels (bottom-left) + scale bar (bottom-right)
        axis_letter = "X" if self._axis == "x" else "Y"
        p.setPen(QColor(t["text_dim"]))
        p.setFont(QFont("sans-serif", 8))
        p.drawText(QRectF(ox_off, oy_off + rend_h + 4, 60, 14), Qt.AlignLeft, f"{axis_letter} →")
        p.drawText(QRectF(ox_off - 34, oy_off - 4, 30, 14), Qt.AlignRight, "Z ↑")
        WorkspaceCanvas._draw_scale_bar(p, scale, ox_off + rend_w, oy_off + rend_h, t)


class DeckViewPanel(QWidget):
    """Top (X/Y) / Side (X/Z) / Side (Y/Z) view switcher over one shared canvas area.

    Owns one WorkspaceCanvas and two DeckSideViewCanvas instances and fans
    every update out to all three, so switching views never shows stale
    data - only the selector's current index changes what's actually
    visible. Exposes the same public API as WorkspaceCanvas (plus the new
    Z-aware setters) so call sites that used to hold a bare WorkspaceCanvas
    can swap in a DeckViewPanel unchanged.
    """

    def __init__(self, t: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = t

        self._top = WorkspaceCanvas(t)
        self._xz  = DeckSideViewCanvas(t, axis="x")
        self._yz  = DeckSideViewCanvas(t, axis="y")

        self._stack = QStackedWidget()
        self._stack.addWidget(self._top)
        self._stack.addWidget(self._xz)
        self._stack.addWidget(self._yz)

        self._view_lbl = QLabel("View:")
        self._selector = QComboBox()
        self._selector.addItems(["Top (X/Y)", "Side (X/Z)", "Side (Y/Z)"])
        self._selector.currentIndexChanged.connect(self._stack.setCurrentIndex)

        sel_row = QHBoxLayout()
        sel_row.setContentsMargins(0, 0, 0, 0)
        sel_row.addWidget(self._view_lbl)
        sel_row.addWidget(self._selector)
        sel_row.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addLayout(sel_row)
        lay.addWidget(self._stack, 1)

        self._apply_style()

    def _apply_style(self) -> None:
        t = self._t
        self.setStyleSheet(
            f"QComboBox {{ background: {t['bg']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 2px 6px; }}"
            f"QLabel {{ color: {t['text_muted']}; background: transparent; }}"
        )

    # --- Fan-out API: forward every update to all 3 canvases ---

    def set_plate_specs(self, labware: dict) -> None:
        for c in (self._top, self._xz, self._yz):
            c.set_plate_specs(labware)

    def load(self, workspace: dict) -> None:
        for c in (self._top, self._xz, self._yz):
            c.load(workspace)

    def clear(self) -> None:
        for c in (self._top, self._xz, self._yz):
            c.clear()

    def set_active_well(self, plate_id: str, well_label: str) -> None:
        for c in (self._top, self._xz, self._yz):
            c.set_active_well(plate_id, well_label)

    def set_current_position(self, x: float, y: float, z: float) -> None:
        self._top.set_current_position(x, y)
        self._xz.set_current_position(x, y, z)
        self._yz.set_current_position(x, y, z)

    def set_limits(
        self,
        x_min: float, x_max: float, y_min: float, y_max: float,
        z_min: float, z_max: float, safe_clearance_z: float,
        crossbar_clearance_above_tip: float | None = None,
        crossbar_y_thickness: float | None = None,
    ) -> None:
        self._top.set_limits(x_min, x_max, y_min, y_max, z_min, z_max)
        self._xz.set_limits(
            x_min, x_max, y_min, y_max, z_min, z_max, safe_clearance_z,
            crossbar_clearance_above_tip, crossbar_y_thickness,
        )
        self._yz.set_limits(
            x_min, x_max, y_min, y_max, z_min, z_max, safe_clearance_z,
            crossbar_clearance_above_tip, crossbar_y_thickness,
        )

    def set_show_details(self, show: bool) -> None:
        """Toggle the deck-boundary overlay - tight-fit to plates by default on all 3 views."""
        for c in (self._top, self._xz, self._yz):
            c.set_show_details(show)

    def set_toolhead_z_engage(self, value: float | None) -> None:
        """Set the active toolhead's engagement depth for the side views' operation-depth marker."""
        self._xz.set_toolhead_z_engage(value)
        self._yz.set_toolhead_z_engage(value)

    def set_theme(self, t: dict) -> None:
        self._t = t
        for c in (self._top, self._xz, self._yz):
            c.set_theme(t)
        self._apply_style()


class WorkspaceLoaderWidget(QWidget):
    """Workspace loader panel - edit/import YAML, send to server, preview canvas."""

    workspace_changed = Signal(dict)   # emits parsed workspace dict on each valid render

    def __init__(
        self,
        t: dict,
        client: "GantryConnection | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            t: Theme dict.
            client: Live GantryConnection used for server operations, or None
                for offline preview-only use.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._t      = t
        self._client = client

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "workspace_loader.ui"))
        f.open(QFile.ReadOnly)
        self._ui = loader.load(f, self)
        f.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ui)

        self._import_btn:   QPushButton    = self._ui.findChild(QPushButton,   "import_btn")
        self._load_btn:     QPushButton    = self._ui.findChild(QPushButton,   "load_btn")
        self._clear_btn:    QPushButton    = self._ui.findChild(QPushButton,   "clear_btn")
        self._apply_btn:    QPushButton    = self._ui.findChild(QPushButton,   "apply_btn")
        self._details_chk:  QCheckBox      = self._ui.findChild(QCheckBox,    "show_details_chk")
        self._yaml_edit:    QPlainTextEdit = self._ui.findChild(QPlainTextEdit,"yaml_edit")
        self._file_lbl:     QLabel         = self._ui.findChild(QLabel,        "file_lbl")
        self._line_lbl:     QLabel         = self._ui.findChild(QLabel,        "line_count_lbl")
        self._status_lbl:   QLabel         = self._ui.findChild(QLabel,        "status_lbl")

        # Insert canvas into canvas_container
        container = self._ui.findChild(QWidget, "canvas_container")
        self._canvas = DeckViewPanel(t, container)
        container.layout().addWidget(self._canvas)

        self._apply_style()
        self._wire()

        if client is None:
            self._load_btn.setEnabled(False)
            self._load_btn.setToolTip("No server connected")
        else:
            client.workspace_op_done.connect(self._on_op_done)
            client.labware_updated.connect(self._canvas.set_plate_specs)
            client.limits_updated.connect(self._canvas.set_limits)

        self._status("")

    def _apply_style(self) -> None:
        t = self._t
        self._ui.setStyleSheet(
            f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}"
            f"QLabel {{ background: transparent; }}"
            f"QFrame#toolbar {{ background: {t['widget_bg']};"
            f" border-bottom: 1px solid {t['border']}; }}"
            f"QPlainTextEdit {{ background: {t['bg']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; }}"
            f"QLabel#file_lbl {{ color: {t['text_muted']}; }}"
            f"QLabel#editor_heading_lbl {{ color: {t['text_muted']}; }}"
            f"QLabel#line_count_lbl {{ color: {t['text_dim']}; }}"
        )
        for btn in (self._import_btn, self._load_btn, self._clear_btn, self._apply_btn):
            btn.setStyleSheet(
                f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
                f" border: 1px solid {t['border']}; border-radius: 4px;"
                f" padding: 3px 10px; }}"
                f"QPushButton:hover {{ border-color: {t['accent']}; }}"
                f"QPushButton:disabled {{ color: {t['text_dim']}; }}"
            )

    def _wire(self) -> None:
        self._import_btn.clicked.connect(self._on_import)
        self._load_btn.clicked.connect(self._on_load_by_name)
        self._clear_btn.clicked.connect(self._on_clear)
        self._apply_btn.clicked.connect(self._on_apply)
        self._yaml_edit.textChanged.connect(self._on_text_changed)
        if self._details_chk:
            self._details_chk.toggled.connect(self._canvas.set_show_details)

    def _on_text_changed(self) -> None:
        text = self._yaml_edit.toPlainText()
        lines = text.count("\n") + 1 if text.strip() else 0
        self._line_lbl.setText(f"{lines} lines" if lines else "")
        self._apply_btn.setEnabled(bool(text.strip()))
        # Live-update canvas as text changes
        self._try_render(text)

    def _try_render(self, text: str) -> None:
        try:
            ws = yaml.safe_load(text)
            if isinstance(ws, dict) and "plates" in ws:
                self._canvas.load(ws)
                self.workspace_changed.emit(ws)
        except Exception:
            pass  # Keep showing last valid render

    def _on_import(self) -> None:
        start_dir = str(_default_workspaces_dir()) if _default_workspaces_dir().is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Workspace YAML", start_dir, "YAML files (*.yaml *.yml);;All files (*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text()
            self._yaml_edit.setPlainText(text)
            self._file_lbl.setText(Path(path).name)
            self._status(f"Loaded {Path(path).name}")
        except Exception as e:
            self._status(f"Error reading file: {e}", error=True)

    def _on_load_by_name(self) -> None:
        if not self._client:
            return
        name, ok = QInputDialog.getText(
            self, "Load Workspace", "Workspace name (see ListWorkspaces for options):"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        self._status(f"Loading '{name}'…")
        self._set_busy(True)
        self._client.load_workspace_by_name(name)

    def _on_apply(self) -> None:
        text = self._yaml_edit.toPlainText().strip()
        if not text:
            return
        self._try_render(text)
        if self._client:
            self._status("Sending workspace to server…")
            self._set_busy(True)
            self._client.apply_workspace_yaml(text)
        else:
            self._status("Canvas updated (no server connected).")

    def _on_clear(self) -> None:
        self._yaml_edit.clear()
        self._file_lbl.setText("")
        self._canvas.clear()
        self._status("Workspace cleared.")

    def _on_op_done(self, ok: bool, msg: str) -> None:
        self._status(msg, error=not ok)
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._apply_btn.setEnabled(
            not busy and bool(self._yaml_edit.toPlainText().strip())
        )
        self._load_btn.setEnabled(not busy and self._client is not None)

    def _status(self, text: str, error: bool = False) -> None:
        if not self._status_lbl:
            return
        self._status_lbl.setText(text)
        t = self._t
        if error:
            self._status_lbl.setStyleSheet(
                f"background: {t['error_bg']}; color: {t['error_text']};"
                f" border-top: 1px solid {t['error_border']}; padding: 6px;"
            )
        else:
            self._status_lbl.setStyleSheet(
                f"background: transparent; color: {t['text_muted']};"
                f" border-top: 1px solid {t['border']}; padding: 4px 6px;"
            )

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and repaint the editor and canvas."""
        self._t = t
        self._canvas.set_theme(t)
        self._apply_style()
        self._status(self._status_lbl.text())
