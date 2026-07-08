"""Homing dialog - two-page flow: ask if already homed, then jog + confirm axis limits."""
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

_PAGE_ASK    = 0
_PAGE_MANUAL = 1


class HomingDialog(QDialog):
    """Loads homing_dialog.ui. Passed a live GantryConnection for issuing commands."""

    def __init__(
        self,
        client: GantryConnection,
        t: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._t      = t

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "homing_dialog.ui"))
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
        self._content = content

        self.setWindowTitle("Gantry Homing")
        self.resize(630, 780)

        # Widgets
        self._stack          = content.findChild(QStackedWidget, "page_stack")
        # page_ask
        self._already_btn    = content.findChild(QPushButton, "already_homed_btn")
        self._need_btn       = content.findChild(QPushButton, "need_homing_btn")
        self._homing_img_lbl = content.findChild(QLabel, "homing_diagram_lbl")
        # page_manual
        self._jog_y_pos      = content.findChild(QPushButton, "jog_y_pos_btn")
        self._jog_y_neg      = content.findChild(QPushButton, "jog_y_neg_btn")
        self._jog_x_pos      = content.findChild(QPushButton, "jog_x_pos_btn")
        self._jog_x_neg      = content.findChild(QPushButton, "jog_x_neg_btn")
        self._jog_z_pos      = content.findChild(QPushButton, "jog_z_pos_btn")
        self._jog_z_neg      = content.findChild(QPushButton, "jog_z_neg_btn")
        self._jog_step       = content.findChild(QDoubleSpinBox, "jog_step_spin")
        self._confirm_xmin   = content.findChild(QPushButton, "confirm_x_min_btn")
        self._confirm_xmax   = content.findChild(QPushButton, "confirm_x_max_btn")
        self._confirm_ymin   = content.findChild(QPushButton, "confirm_y_min_btn")
        self._confirm_ymax   = content.findChild(QPushButton, "confirm_y_max_btn")
        self._confirm_zref   = content.findChild(QPushButton, "confirm_z_ref_btn")
        self._back_btn       = content.findChild(QPushButton, "back_to_ask_btn")
        self._finish_btn     = content.findChild(QPushButton, "finish_homing_btn")
        self._xz_img         = content.findChild(QLabel, "diagram_xz_lbl")
        self._y_img          = content.findChild(QLabel, "diagram_y_lbl")

        self._load_diagrams()
        self._apply_theme()
        self._wire()
        self._client.experiment_active_changed.connect(self._on_experiment_active)
        self._stack.setCurrentIndex(_PAGE_ASK)

    def _load_diagrams(self) -> None:
        def _set(lbl: QLabel | None, name: str, w: int, h: int) -> None:
            if not lbl:
                return
            p = _ASSET_DIR / name
            if p.exists():
                px = QPixmap(str(p))
                lbl.setPixmap(px.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                lbl.setText("")

        _set(self._homing_img_lbl, "gantry_home_reference.png", 480, 480)
        _set(self._xz_img,         "gantry_home_XZ.png",        290, 200)
        _set(self._y_img,          "gantry_home_Y.png",         290, 200)

    def _apply_theme(self) -> None:
        t = self._t
        self.setStyleSheet(
            f"QDialog {{ background: {t['bg_surface']}; }}"
            f"QGroupBox {{ color: {t['text']}; border: 1px solid {t['border']};"
            f" border-radius: 4px; margin-top: 8px; padding-top: 8px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
            f"QLabel {{ color: {t['text']}; }}"
            f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ border-color: {t['accent']}; }}"
            f"QDoubleSpinBox {{ background: {t['bg']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 2px 4px; }}"
        )
        if self._finish_btn:
            self._finish_btn.setStyleSheet(
                f"QPushButton {{ background: {t['accent']}; color: {t['accent_text']};"
                f" border: none; border-radius: 4px; padding: 6px 16px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: {t['accent']}; opacity: 0.9; }}"
            )

    def _wire(self) -> None:
        # page_ask
        if self._already_btn:
            self._already_btn.clicked.connect(self.accept)
        if self._need_btn:
            self._need_btn.clicked.connect(self._start_manual)

        # Jog
        step = lambda: self._jog_step.value() if self._jog_step else 1.0
        if self._jog_x_pos: self._jog_x_pos.clicked.connect(lambda: self._client.jog(dx= step()))
        if self._jog_x_neg: self._jog_x_neg.clicked.connect(lambda: self._client.jog(dx=-step()))
        if self._jog_y_pos: self._jog_y_pos.clicked.connect(lambda: self._client.jog(dy= step()))
        if self._jog_y_neg: self._jog_y_neg.clicked.connect(lambda: self._client.jog(dy=-step()))
        if self._jog_z_pos: self._jog_z_pos.clicked.connect(lambda: self._client.jog(dz= step()))
        if self._jog_z_neg: self._jog_z_neg.clicked.connect(lambda: self._client.jog(dz=-step()))

        # Confirm positions - also mark each button green when clicked
        def _confirm(call, btn):
            def _inner():
                call()
                self._mark_confirmed(btn)
            return _inner

        if self._confirm_xmin: self._confirm_xmin.clicked.connect(_confirm(self._client.confirm_x_min,       self._confirm_xmin))
        if self._confirm_xmax: self._confirm_xmax.clicked.connect(_confirm(self._client.confirm_x_max,       self._confirm_xmax))
        if self._confirm_ymin: self._confirm_ymin.clicked.connect(_confirm(self._client.confirm_y_min,       self._confirm_ymin))
        if self._confirm_ymax: self._confirm_ymax.clicked.connect(_confirm(self._client.confirm_y_max,       self._confirm_ymax))
        if self._confirm_zref: self._confirm_zref.clicked.connect(_confirm(self._client.confirm_z_reference, self._confirm_zref))

        # Navigation
        if self._back_btn:   self._back_btn.clicked.connect(
            lambda: self._stack.setCurrentIndex(_PAGE_ASK)
        )
        if self._finish_btn: self._finish_btn.clicked.connect(self._finish)

    def _on_experiment_active(self, active: bool) -> None:
        """Disable jog/confirm controls if a script acquires the lock while this dialog is open."""
        self._lock_banner.setVisible(active)
        for btn in (
            self._jog_x_pos, self._jog_x_neg, self._jog_y_pos, self._jog_y_neg,
            self._jog_z_pos, self._jog_z_neg,
            self._confirm_xmin, self._confirm_xmax,
            self._confirm_ymin, self._confirm_ymax,
            self._confirm_zref, self._finish_btn,
        ):
            if btn:
                btn.setEnabled(not active)

    def _mark_confirmed(self, btn: QPushButton) -> None:
        t = self._t
        btn.setStyleSheet(
            f"QPushButton {{ background: {t['dot_ok']}; color: #ffffff;"
            f" border: none; border-radius: 4px; padding: 4px 10px; font-weight: bold; }}"
        )

    def _start_manual(self) -> None:
        self._client.start_manual_homing()
        self._stack.setCurrentIndex(_PAGE_MANUAL)

    def _finish(self) -> None:
        self._client.finish_homing()
        self.accept()

    def closeEvent(self, event) -> None:
        try:
            self._client.experiment_active_changed.disconnect(self._on_experiment_active)
        except RuntimeError:
            pass
        super().closeEvent(event)
