"""
Toolhead calibration dialog - 3-page flow.
User jogs to 4 rim points; 4-point average gives the actual well centre in machine coordinates.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QLabel, QPushButton,
    QStackedWidget, QVBoxLayout,
)
from PySide6.QtUiTools import QUiLoader

from .connection import GantryConnection

_UI_DIR    = Path(__file__).parent / "ui"
_ASSET_DIR = Path(__file__).parent / "assets"

_PAGE_INTRO   = 0
_PAGE_CORNERS = 1
_PAGE_RESULTS = 2

_CORNER_NAMES = ["NW", "NE", "SE", "SW"]
_CORNER_INSTRUCTIONS = [
    "Jog the tip to the North West rim of the reference well, then confirm.",
    "Jog the tip to the North East rim of the reference well, then confirm.",
    "Jog the tip to the South East rim of the reference well, then confirm.",
    "Jog the tip to the South West rim of the reference well, then confirm.",
]


class ToolheadCalibrationDialog(QDialog):
    """Three-page dialog for calibrating a toolhead by jogging to four rim points of a reference well."""

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
        self._cur_x = self._cur_y = 0.0

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "toolhead_calibration_dialog.ui"))
        f.open(QFile.ReadOnly)
        content = loader.load(f, self)
        f.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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
        self._redo_btn     = content.findChild(QPushButton,  "redo_cal_btn")
        self._accept_btn   = content.findChild(QPushButton,  "accept_cal_btn")

        self._load_corner_diagram()
        if self._th_lbl:
            self._th_lbl.setText(f"Calibrating: {toolhead_name}")
        if self._ref_lbl:
            self._ref_lbl.setText("Reference well: move to well manually before starting")

        self._apply_theme()
        self._wire()
        self._stack.setCurrentIndex(_PAGE_INTRO)

        self._client.position_updated.connect(self._on_position)


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
        for btn in (self._start_btn, self._confirm_btn, self._accept_btn):
            if btn:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {t['accent']}; color: {t['accent_text']};"
                    f" border: none; border-radius: 4px; padding: 6px 16px; font-weight: bold; }}"
                )


    def _wire(self) -> None:
        step = lambda: self._jog_step.value() if self._jog_step else 0.5

        if self._start_btn:  self._start_btn.clicked.connect(self._start)
        if self._jog_x_pos:  self._jog_x_pos.clicked.connect(lambda: self._client.jog(dx= step()))
        if self._jog_x_neg:  self._jog_x_neg.clicked.connect(lambda: self._client.jog(dx=-step()))
        if self._jog_y_pos:  self._jog_y_pos.clicked.connect(lambda: self._client.jog(dy= step()))
        if self._jog_y_neg:  self._jog_y_neg.clicked.connect(lambda: self._client.jog(dy=-step()))
        if self._jog_z_pos:  self._jog_z_pos.clicked.connect(lambda: self._client.jog(dz= step()))
        if self._jog_z_neg:  self._jog_z_neg.clicked.connect(lambda: self._client.jog(dz=-step()))
        if self._abort_btn:  self._abort_btn.clicked.connect(self.reject)
        if self._confirm_btn: self._confirm_btn.clicked.connect(self._confirm_corner)
        if self._redo_btn:   self._redo_btn.clicked.connect(self._redo)
        if self._accept_btn: self._accept_btn.clicked.connect(self.accept)


    def _start(self) -> None:
        self._corner_idx = 0
        self._corners    = []
        self._refresh_corner_ui()
        self._stack.setCurrentIndex(_PAGE_CORNERS)

    def _refresh_corner_ui(self) -> None:
        i = self._corner_idx
        if self._corner_title:
            self._corner_title.setText(f"Point {i + 1} of 4 - {_CORNER_NAMES[i]} rim")
        if self._corner_instr:
            self._corner_instr.setText(_CORNER_INSTRUCTIONS[i])
        if self._confirm_btn:
            self._confirm_btn.setText(f"Confirm Rim Point {i + 1} ✓")

        for j, lbl in enumerate(self._corner_status):
            if not lbl:
                continue
            if j < i:
                lbl.setText(f"✓  {_CORNER_NAMES[j]} rim")
            elif j == i:
                lbl.setText(f"→  {_CORNER_NAMES[j]} rim")
            else:
                lbl.setText(f"○  {_CORNER_NAMES[j]} rim")

    def _confirm_corner(self) -> None:
        self._corners.append((self._cur_x, self._cur_y))
        if self._corner_status[self._corner_idx]:
            self._corner_status[self._corner_idx].setText(
                f"✓  {_CORNER_NAMES[self._corner_idx]} rim"
            )
        self._corner_idx += 1
        if self._corner_idx >= 4:
            self._show_results()
        else:
            self._refresh_corner_ui()

    def _show_results(self) -> None:
        cx = sum(p[0] for p in self._corners) / 4
        cy = sum(p[1] for p in self._corners) / 4
        if self._offset_x_lbl:
            self._offset_x_lbl.setText(f"X centre:   {cx:+.3f}  mm")
        if self._offset_y_lbl:
            self._offset_y_lbl.setText(f"Y centre:   {cy:+.3f}  mm")
        self._stack.setCurrentIndex(_PAGE_RESULTS)

    def _redo(self) -> None:
        self._start()


    def _on_position(self, x: float, y: float, _z: float) -> None:
        self._cur_x, self._cur_y = x, y

    def closeEvent(self, event) -> None:
        try:
            self._client.position_updated.disconnect(self._on_position)
        except RuntimeError:
            pass
        super().closeEvent(event)
