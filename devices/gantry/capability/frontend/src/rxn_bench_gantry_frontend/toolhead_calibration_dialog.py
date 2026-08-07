"""
Toolhead calibration dialog - 4-page flow.
Auto-moves to the calibration reference well, then to the plate's other 3
corner wells in turn (move_to_well() resolves each one's exact position
server-side, correctly handling rotation/origin_mode - no client-side
geometry needed). A small manual jog centres the tip at each; the 4-point
average gives the measured well centre in machine coordinates, compared
against the average of those same 4 wells' nominal positions. Then jogs the
tip down to touch the Z=0 reference surface for the Z offset.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from PySide6.QtCore import QFile, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QLabel, QPushButton,
    QStackedWidget, QVBoxLayout,
)
from PySide6.QtUiTools import QUiLoader

from .connection import GantryConnection
from .workspace_loader import resolve_reference_plate_height

_UI_DIR    = Path(__file__).parent / "ui"
_ASSET_DIR = Path(__file__).parent / "assets"

_WELL_LABEL_RE = re.compile(r'^([A-Za-z])(\d+)$')
_PAPER_THICKNESS_MM = 0.1  # standard printer paper, rough estimate


def _corner_wells_for(workspace_yaml: str, labware: dict) -> list[str]:
    """Resolve a workspace's calibration_reference_well into 4 corner well labels.

    The reference well is treated as one corner of its plate's row/column
    grid; the other 3 corners are found by flipping row and/or column to the
    opposite end (e.g. reference 'H1' on an 8x12 plate -> 'H12', 'A1', 'A12').
    Only grid arithmetic happens here - move_to_well() resolves each label's
    actual position server-side, so rotation/origin_mode is handled exactly
    the same way it is for every other well, with no geometry duplicated here.

    Args:
        workspace_yaml: Raw YAML of the active workspace (as returned by
            GetWorkspaceYaml), or "" if none is loaded.
        labware: ``{plate_type: geometry dict}`` as returned by fetch_labware().

    Returns:
        4 "plate_id/well_label" corner wells, or a single-entry list with just
        the reference well if the grid can't be resolved (unknown plate type,
        missing rows/columns, malformed label), or [] if there's no
        calibration_reference_well configured at all.
    """
    corners: list[str] = []
    ref_well = ""
    try:
        data = yaml.safe_load(workspace_yaml) or {} if workspace_yaml else {}
        ref_well = (data.get("calibration_reference_well") or "").strip()
        if ref_well and "/" in ref_well:
            plate_id, well_label = (p.strip() for p in ref_well.split("/", 1))
            plates = data.get("plates", []) or []
            plate = next((p for p in plates if p.get("id") == plate_id), None)
            m = _WELL_LABEL_RE.match(well_label.upper())
            if plate and m:
                plate_type = plate.get("plate_type")
                geom = labware.get(plate_type) or {}
                rows, cols = geom.get("rows"), geom.get("columns")
                if rows and cols:
                    row_idx = ord(m.group(1)) - ord('A')
                    col_idx = int(m.group(2)) - 1
                    opp_row = rows - 1 - row_idx
                    opp_col = cols - 1 - col_idx
                    grid = [
                        (row_idx, col_idx),       # reference well itself
                        (row_idx, opp_col),       # same row, opposite column
                        (opp_row, col_idx),       # opposite row, same column
                        (opp_row, opp_col),       # diagonally opposite
                    ]
                    corners = [f"{plate_id}/{chr(ord('A') + r)}{c + 1}" for r, c in grid]
    except Exception:
        corners = []
    if not corners and ref_well:
        corners = [ref_well]  # fall back to single-well calibration
    return corners


class _CornerWellsWorker(QThread):
    """Runs _corner_wells_for() off the GUI thread (fetch_workspace_yaml/fetch_labware block).

    Also resolves the reference plate's top-surface height from the same
    fetched workspace/labware data, for the Z-touch page's optional
    hover-over-reference-plate calibration technique - no separate round-trip.
    """

    done = Signal(list, object)  # (4 "plate_id/well_label" corners; [] if unresolvable), (plate_id, height_mm) or None

    def __init__(self, client: GantryConnection) -> None:
        super().__init__()
        self._client = client

    def run(self) -> None:
        raw = self._client.fetch_workspace_yaml()
        labware = self._client.fetch_labware() if raw else {}
        self.done.emit(
            _corner_wells_for(raw, labware),
            resolve_reference_plate_height(raw, labware),
        )

class _CalibrateWorker(QThread):
    """Runs the blocking calibrate_toolhead_tip() call off the GUI thread."""

    done = Signal(object)  # (nominal_x, nominal_y, tip_x, tip_y) tuple, or None on failure

    def __init__(self, client: GantryConnection, measured_x: float, measured_y: float, wells: str) -> None:
        super().__init__()
        self._client = client
        self._measured_x = measured_x
        self._measured_y = measured_y
        self._wells = wells

    def run(self) -> None:
        self.done.emit(
            self._client.calibrate_toolhead_tip(self._measured_x, self._measured_y, self._wells)
        )

_PAGE_INTRO   = 0
_PAGE_CORNERS = 1
_PAGE_RESULTS = 2
_PAGE_Z_TOUCH = 3


class ToolheadCalibrationDialog(QDialog):
    """Dialog for calibrating a toolhead by centring the tip at a plate's 4 corner wells in turn."""

    def __init__(
        self,
        client: GantryConnection,
        toolhead_name: str,
        t: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._client        = client
        self._toolhead_name = toolhead_name
        self._t             = t
        self._corner_idx    = 0
        self._corners: list[tuple[float, float]] = []
        self._cur_x = self._cur_y = self._cur_z = 0.0
        self._measured_x = self._measured_y = 0.0
        # jog() is fire-and-forget and the position stream only refreshes
        # every ~0.5s server-side, so a jog click followed quickly by Confirm
        # (the natural workflow when eyeballing physical alignment through a
        # camera rather than watching the software's numeric readout) can
        # capture the *pre-jog* position - producing a corrupted average that
        # silently misses every well by the same wrong amount. Gate Confirm
        # on having seen at least one fresh position sample since the last jog.
        self._position_settled = True

        self._corner_wells: list[str] = []  # 4 "plate_id/well_label" entries, in visiting order
        # True while a move_to_well() auto-approach is in flight for the current corner.
        self._pending_auto_move = False
        # move_to_well() is fire-and-forget, so there's a window between
        # firing the request and the server actually starting it where the
        # action stream is still emitting a *stale* "Standby" left over from
        # before this move was ever requested. Treating that stale sample as
        # completion meant the wizard "finished" the move instantly, capturing
        # the *old* position - which looked like every corner travelled to the
        # same spot. Require seeing the move actually start (a non-Standby
        # action) before a later Standby counts as completion.
        self._auto_move_started = False

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "toolhead_calibration_dialog.ui"))
        f.open(QFile.ReadOnly)
        content = loader.load(f, self)
        f.close()

        self._lock_banner = QLabel(
            "An experiment has acquired the lock - jog/confirm controls are disabled."
        )
        self._lock_banner.setWordWrap(True)
        self._lock_banner.setStyleSheet(
            "background: #7c5200; color: #ffe0a0; border-radius: 4px; padding: 6px 8px;"
        )
        self._lock_banner.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._lock_banner)
        layout.addWidget(content)
        self.setWindowTitle("Toolhead Calibration")
        self.resize(520, 500)

        self._stack = content.findChild(QStackedWidget, "page_stack")

        # page 0
        self._th_lbl       = content.findChild(QLabel,       "toolhead_name_lbl")
        self._ref_lbl      = content.findChild(QLabel,       "cal_ref_well_lbl")
        self._start_btn    = content.findChild(QPushButton,  "start_cal_btn")

        # page 1
        self._corner_title = content.findChild(QLabel,       "corner_title_lbl")
        self._corner_instr = content.findChild(QLabel,       "corner_instruction_lbl")
        self._corner_status = [
            content.findChild(QLabel, f"corner{i + 1}_status_lbl") for i in range(4)
        ]
        self._jog_x_pos    = content.findChild(QPushButton,  "jog_x_pos_btn")
        self._jog_x_neg    = content.findChild(QPushButton,  "jog_x_neg_btn")
        self._jog_y_pos    = content.findChild(QPushButton,  "jog_y_pos_btn")
        self._jog_y_neg    = content.findChild(QPushButton,  "jog_y_neg_btn")
        self._jog_z_pos    = content.findChild(QPushButton,  "jog_z_pos_btn")
        self._jog_z_neg    = content.findChild(QPushButton,  "jog_z_neg_btn")
        self._jog_step     = content.findChild(QDoubleSpinBox, "jog_step_spin")
        self._confirm_btn  = content.findChild(QPushButton,  "confirm_corner_btn")
        self._abort_btn    = content.findChild(QPushButton,  "abort_cal_btn")

        # corner diagram
        self._corner_diagram_lbl = content.findChild(QLabel, "corner_diagram_lbl")

        # page 2
        self._offset_x_lbl = content.findChild(QLabel,      "offset_x_lbl")
        self._offset_y_lbl = content.findChild(QLabel,      "offset_y_lbl")
        self._computed_offset_lbl = content.findChild(QLabel, "computed_offset_lbl")
        self._redo_btn     = content.findChild(QPushButton,  "redo_cal_btn")
        self._accept_btn   = content.findChild(QPushButton,  "accept_cal_btn")
        # First Accept click: run calibration and show the result. Second
        # click (button relabels itself): proceed to Z calibration - gives
        # the operator a chance to actually read the numbers before moving on.
        self._calibration_done = False

        # page 3 (Z touch)
        self._z_touch_body   = content.findChild(QLabel,       "z_touch_body")
        self._z_current_lbl  = content.findChild(QLabel,       "z_current_lbl")
        self._z_jog_pos      = content.findChild(QPushButton,  "z_jog_pos_btn")
        self._z_jog_neg      = content.findChild(QPushButton,  "z_jog_neg_btn")
        self._z_jog_step     = content.findChild(QDoubleSpinBox, "z_jog_step_spin")
        self._abort_z_btn    = content.findChild(QPushButton,  "abort_z_btn")
        self._confirm_z_btn  = content.findChild(QPushButton,  "confirm_z_touch_btn")
        self._z_hover_info_lbl  = content.findChild(QLabel,    "z_hover_info_lbl")
        self._hover_reference_chk = content.findChild(QCheckBox, "hover_reference_chk")
        self._paper_shim_chk   = content.findChild(QCheckBox,  "paper_shim_chk")
        self._z_ref_height     = 0.0   # reference plate's top surface height, if resolved
        self._z_ref_plate_id: str | None = None

        self._load_corner_diagram()
        if self._th_lbl:
            self._th_lbl.setText(f"Calibrating: {toolhead_name}")
        if self._ref_lbl:
            self._ref_lbl.setText("Reference well: loading…")

        self._apply_theme()
        self._wire()
        self._stack.setCurrentIndex(_PAGE_INTRO)

        self._client.position_updated.connect(self._on_position)
        self._client.experiment_active_changed.connect(self._on_experiment_active)
        self._client.action_changed.connect(self._on_action_changed)
        self._client.error_occurred.connect(self._on_error)

        self._corner_wells_worker = _CornerWellsWorker(self._client)
        self._corner_wells_worker.done.connect(self._on_corner_wells_loaded)
        self._corner_wells_worker.start()

    def _on_corner_wells_loaded(self, corner_wells: list[str], ref_height: object) -> None:
        """Show the calibration reference well and cache the 4 corner wells to visit.

        Without showing the well name, an operator had no way to verify they
        were even looking at the right physical location - jogging to the
        wrong spot and calibrating against a nominal position that doesn't
        match where they are produces nonsensical tip offsets.
        """
        self._corner_wells = corner_wells
        if self._ref_lbl:
            if corner_wells:
                self._ref_lbl.setText(
                    f"Reference well: {corner_wells[0]} - Start will move through "
                    f"{len(corner_wells)} corner well(s) automatically"
                )
            else:
                self._ref_lbl.setText("Reference well: unknown - no workspace loaded or no reference well configured")

        if ref_height is not None:
            plate_id, height = ref_height
            self._z_ref_plate_id = plate_id
            self._z_ref_height = height
            if self._hover_reference_chk:
                self._hover_reference_chk.setEnabled(True)
                self._hover_reference_chk.setToolTip(
                    f"Uses {plate_id!r}'s configured top surface height ({height:.1f}mm above the deck)."
                )
            if self._z_hover_info_lbl:
                self._z_hover_info_lbl.setText(
                    f"Reference plate {plate_id!r} top surface: {height:.1f}mm above the deck."
                )
        else:
            self._z_ref_plate_id = None
            self._z_ref_height = 0.0
            if self._hover_reference_chk:
                self._hover_reference_chk.setEnabled(False)
                self._hover_reference_chk.setChecked(False)
            if self._z_hover_info_lbl:
                self._z_hover_info_lbl.setText("")


    def _load_corner_diagram(self) -> None:
        lbl = self._corner_diagram_lbl
        if not lbl:
            return
        p = _ASSET_DIR / "toolhead_calibration_reference.png"
        if p.exists():
            px = QPixmap(str(p))
            lbl.setPixmap(px.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl.setText("")


    def _apply_theme(self) -> None:
        t = self._t
        self.setStyleSheet(
            f"QDialog  {{ background: {t['bg_surface']}; }}"
            f"QLabel   {{ color: {t['text']}; }}"
            f"QGroupBox {{ color: {t['text']}; border: 1px solid {t['border']};"
            f" border-radius: 4px; margin-top: 8px; padding-top: 8px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
            f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ border-color: {t['accent']}; }}"
            f"QDoubleSpinBox {{ background: {t['bg']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 2px 4px; }}"
        )
        for btn in (self._start_btn, self._confirm_btn, self._accept_btn, self._confirm_z_btn):
            if btn:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {t['accent']}; color: {t['accent_text']};"
                    f" border: none; border-radius: 4px; padding: 6px 16px; font-weight: bold; }}"
                )


    def _wire(self) -> None:
        step = lambda: self._jog_step.value() if self._jog_step else 0.5

        if self._start_btn:  self._start_btn.clicked.connect(self._start)
        if self._jog_x_pos:  self._jog_x_pos.clicked.connect(lambda: self._jog(dx= step()))
        if self._jog_x_neg:  self._jog_x_neg.clicked.connect(lambda: self._jog(dx=-step()))
        if self._jog_y_pos:  self._jog_y_pos.clicked.connect(lambda: self._jog(dy= step()))
        if self._jog_y_neg:  self._jog_y_neg.clicked.connect(lambda: self._jog(dy=-step()))
        if self._jog_z_pos:  self._jog_z_pos.clicked.connect(lambda: self._jog(dz= step()))
        if self._jog_z_neg:  self._jog_z_neg.clicked.connect(lambda: self._jog(dz=-step()))
        if self._abort_btn:  self._abort_btn.clicked.connect(self.reject)
        if self._confirm_btn: self._confirm_btn.clicked.connect(self._confirm_corner)
        if self._redo_btn:   self._redo_btn.clicked.connect(self._redo)
        if self._accept_btn: self._accept_btn.clicked.connect(self._accept_xy_calibration)

        z_step = lambda: self._z_jog_step.value() if self._z_jog_step else 0.5
        if self._z_jog_pos:   self._z_jog_pos.clicked.connect(lambda: self._jog(dz= z_step()))
        if self._z_jog_neg:   self._z_jog_neg.clicked.connect(lambda: self._jog(dz=-z_step()))
        if self._abort_z_btn: self._abort_z_btn.clicked.connect(self.reject)
        if self._confirm_z_btn: self._confirm_z_btn.clicked.connect(self._accept_z_calibration)
        if self._hover_reference_chk:
            self._hover_reference_chk.toggled.connect(self._update_z_touch_instructions)

    def _update_z_touch_instructions(self) -> None:
        """Swap the touch-vs-hover instruction text to match the selected mode."""
        if not self._z_touch_body:
            return
        if self._hover_reference_chk and self._hover_reference_chk.isChecked():
            self._z_touch_body.setText(
                f"Jog the tip down to hover just above {self._z_ref_plate_id!r}'s top surface "
                f"({self._z_ref_height:.1f}mm above the deck) - do not touch it, then confirm. "
                "The current carriage Z, minus that known height, becomes this toolhead's "
                "measured tip_offset_z."
            )
        else:
            self._z_touch_body.setText(
                "Jog the tip straight down until it just touches the deck / Z=0 reference "
                "surface, then confirm. The current carriage Z becomes this toolhead's "
                "measured tip_offset_z."
            )

    def _jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        """Jog, then block Confirm until a position sample newer than this jog arrives.

        jog() itself is fire-and-forget, so without this an operator who jogs
        and immediately confirms (the natural workflow when judging alignment
        by eye/camera rather than watching the number) can capture a stale,
        pre-jog position.
        """
        self._position_settled = False
        if self._confirm_btn:
            self._confirm_btn.setEnabled(False)
        if self._confirm_z_btn:
            self._confirm_z_btn.setEnabled(False)
        self._client.jog(dx=dx, dy=dy, dz=dz)


    def _start(self) -> None:
        self._corner_idx = 0
        self._corners    = []
        self._calibration_done = False
        if self._accept_btn:
            self._accept_btn.setText("Accept & Continue ->")
        self._stack.setCurrentIndex(_PAGE_CORNERS)
        if self._corner_wells:
            self._move_to_corner(0)
        else:
            self._refresh_corner_ui()

    def _set_corner_controls_enabled(self, enabled: bool) -> None:
        for btn in (
            self._jog_x_pos, self._jog_x_neg, self._jog_y_pos, self._jog_y_neg,
            self._jog_z_pos, self._jog_z_neg,
        ):
            if btn:
                btn.setEnabled(enabled)
        if self._confirm_btn:
            self._confirm_btn.setEnabled(enabled and self._position_settled)

    def _move_to_corner(self, i: int) -> None:
        """Auto-move to corner well *i* via move_to_well() - no client-side geometry needed.

        move_to_well() already resolves the well's exact position server-side,
        correctly handling rotation/origin_mode the same way it does for any
        other well - so unlike an earlier version of this dialog, there's no
        rotation math to get wrong here. It also docks Z at that well's actual
        opening (the plate's top surface) rather than a generic clearance
        height, so the tip already sits at/near the well by the time this
        move completes - jogging here is fine centring, not a big descent.
        override_unvalidated=True is required for two independent reasons:
        this toolhead's tip offsets aren't measured yet (the whole point of
        this wizard), and its *configured* z_engage may exceed this
        particular calibration plate's well depth - harmless here since this
        wizard only ever positions at the opening and never calls
        engage_tool, but move_to_well can't tell the two reasons apart.
        """
        well = self._corner_wells[i]
        self._set_corner_controls_enabled(False)
        if self._corner_instr:
            self._corner_instr.setText(f"Moving to corner well {well}…")
        self._pending_auto_move = True
        self._auto_move_started = False
        self._position_settled = False
        self._client.move_to_well(well, override_unvalidated=True)

    def _on_action_changed(self, action: str) -> None:
        if not self._pending_auto_move:
            return
        if not self._auto_move_started:
            # Wait for a non-Standby sample - proof the server has actually
            # started this move - before trusting any subsequent Standby.
            if action != "Standby":
                self._auto_move_started = True
            return
        if action != "Standby":
            return
        self._pending_auto_move = False
        self._auto_move_started = False
        self._set_corner_controls_enabled(True)
        self._refresh_corner_ui()

    def _on_error(self, message: str) -> None:
        """Recover the wizard's controls if an auto-positioning move fails.

        Without this, a rejected MoveToWell (e.g. bounds) would leave
        jog/confirm permanently disabled with no way to proceed manually.
        """
        if not self._pending_auto_move:
            return
        self._pending_auto_move = False
        self._auto_move_started = False
        self._set_corner_controls_enabled(True)
        if self._corner_instr:
            self._corner_instr.setText(f"Auto-move failed ({message}) - jog manually, then confirm.")

    def _refresh_corner_ui(self) -> None:
        i = self._corner_idx
        well = self._corner_wells[i] if i < len(self._corner_wells) else "?"
        if self._corner_title:
            self._corner_title.setText(f"Corner {i + 1} of {len(self._corner_wells)} - well {well}")
        if self._corner_instr:
            self._corner_instr.setText(f"Jog the tip to the centre of well {well}, then confirm.")
        if self._confirm_btn:
            self._confirm_btn.setText(f"Confirm Corner {i + 1} ✓")

        for j, lbl in enumerate(self._corner_status):
            if not lbl:
                continue
            label = self._corner_wells[j] if j < len(self._corner_wells) else "-"
            if j < i:
                lbl.setText(f"✓  {label}")
            elif j == i:
                lbl.setText(f"->  {label}")
            else:
                lbl.setText(f"○  {label}")

    def _confirm_corner(self) -> None:
        if not self._position_settled:
            return  # button should be disabled in this state; belt and suspenders
        self._corners.append((self._cur_x, self._cur_y))
        if self._corner_status[self._corner_idx]:
            self._corner_status[self._corner_idx].setText(f"✓  {self._corner_wells[self._corner_idx]}")
        self._corner_idx += 1
        if self._corner_idx >= len(self._corner_wells):
            self._show_results()
        else:
            self._move_to_corner(self._corner_idx)

    def _show_results(self) -> None:
        n = len(self._corners)
        cx = sum(p[0] for p in self._corners) / n
        cy = sum(p[1] for p in self._corners) / n
        self._measured_x, self._measured_y = cx, cy
        if self._offset_x_lbl:
            self._offset_x_lbl.setText(f"Measured well centre X:   {cx:+.3f}  mm  (avg of {n})")
        if self._offset_y_lbl:
            self._offset_y_lbl.setText(f"Measured well centre Y:   {cy:+.3f}  mm  (avg of {n})")
        if self._computed_offset_lbl:
            self._computed_offset_lbl.setText("Nominal well centre and tip offset:   not yet calculated")
        self._stack.setCurrentIndex(_PAGE_RESULTS)

    def _redo(self) -> None:
        self._start()

    def _accept_xy_calibration(self) -> None:
        """First click: run calibration and show the result. Second click: proceed to Z.

        Splitting this into two clicks (rather than auto-advancing) is what
        actually lets the operator *see* the nominal well centre and the
        resulting tip_x/tip_y before moving on, instead of them flashing by
        or being guessed from a delayed stream sample.
        """
        if self._calibration_done:
            self._stack.setCurrentIndex(_PAGE_Z_TOUCH)
            return
        if self._accept_btn:
            self._accept_btn.setEnabled(False)
        if self._computed_offset_lbl:
            self._computed_offset_lbl.setText("Calculating…")
        self._calibrate_worker = _CalibrateWorker(
            self._client, self._measured_x, self._measured_y, "|".join(self._corner_wells)
        )
        self._calibrate_worker.done.connect(self._on_calibration_result)
        self._calibrate_worker.start()

    def _on_calibration_result(self, result: object) -> None:
        if self._accept_btn:
            self._accept_btn.setEnabled(True)
        if result is None:
            if self._computed_offset_lbl:
                self._computed_offset_lbl.setText(
                    "Calibration failed - see error above. Redo or retry."
                )
            return
        nominal_x, nominal_y, tip_x, tip_y = result
        if self._computed_offset_lbl:
            self._computed_offset_lbl.setText(
                f"Nominal well centre:   ({nominal_x:+.3f}, {nominal_y:+.3f})  mm\n"
                f"Tip offset saved:      tip_x={tip_x:+.3f}mm   tip_y={tip_y:+.3f}mm"
            )
        self._calibration_done = True
        if self._accept_btn:
            self._accept_btn.setText("Continue to Z Calibration ->")

    def _accept_z_calibration(self) -> None:
        """Compute and send this toolhead's tip_offset_z, then close.

        Touch mode (default): the tip is physically at the deck's Z=0, so
        the current carriage Z *is* tip_offset_z directly - unchanged from
        before. Hover mode: the tip is instead at the reference plate's known
        top-surface height H (not physically touched), so tip_offset_z is
        derived as current_Z - H. Either way, a checked paper shim means the
        tip is actually shim-thickness *above* the touched/hovered surface,
        so that thickness is added back in before subtracting.
        """
        if not self._position_settled:
            return
        surface_height = 0.0
        if self._hover_reference_chk and self._hover_reference_chk.isChecked():
            surface_height = self._z_ref_height
        if self._paper_shim_chk and self._paper_shim_chk.isChecked():
            surface_height += _PAPER_THICKNESS_MM
        self._client.calibrate_toolhead_tip_z(self._cur_z - surface_height)
        self.accept()

    def _on_position(self, x: float, y: float, z: float) -> None:
        self._cur_x, self._cur_y, self._cur_z = x, y, z
        if self._z_current_lbl:
            self._z_current_lbl.setText(f"Current Z:   {z:+.3f}  mm")
        if not self._position_settled:
            self._position_settled = True
            if self._confirm_btn:
                self._confirm_btn.setEnabled(True)
            if self._confirm_z_btn:
                self._confirm_z_btn.setEnabled(True)

    def _on_experiment_active(self, active: bool) -> None:
        """Disable jog/confirm controls if a script acquires the lock while this dialog is open."""
        self._lock_banner.setVisible(active)
        for btn in (
            self._start_btn,
            self._jog_x_pos, self._jog_x_neg, self._jog_y_pos, self._jog_y_neg,
            self._jog_z_pos, self._jog_z_neg,
            self._z_jog_pos, self._z_jog_neg,
        ):
            if btn:
                btn.setEnabled(not active)
        # Confirm buttons stay gated on _position_settled even when the lock releases.
        confirm_enabled = (not active) and self._position_settled
        if self._confirm_btn:
            self._confirm_btn.setEnabled(confirm_enabled)
        if self._confirm_z_btn:
            self._confirm_z_btn.setEnabled(confirm_enabled)

    def closeEvent(self, event) -> None:
        try:
            self._client.position_updated.disconnect(self._on_position)
        except RuntimeError:
            pass
        try:
            self._client.experiment_active_changed.disconnect(self._on_experiment_active)
        except RuntimeError:
            pass
        try:
            self._client.action_changed.disconnect(self._on_action_changed)
        except RuntimeError:
            pass
        try:
            self._client.error_occurred.disconnect(self._on_error)
        except RuntimeError:
            pass
        super().closeEvent(event)
