"""Gantry control widget: connection bar, left sidebar (toolheads/homing/position), right workspace panel."""
from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtCore import QFile, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)
from PySide6.QtUiTools import QUiLoader

from ...discovery import DiscoveredServer
from ...sila_client import SilaClient
from .workspace_loader import WorkspaceLoaderWidget

_UI_DIR = Path(__file__).parent / "ui"


class _ToolheadListWorker(QThread):
    done = Signal(list)  # list[tuple[str, str]]

    def __init__(self, client: SilaClient) -> None:
        super().__init__()
        self._client = client

    def run(self) -> None:
        self.done.emit(self._client.fetch_toolhead_list())


class GantryWidget(QWidget):
    """Full gantry control panel, registered for feature 'Gantry'."""

    FEATURE_ID = "edu.iastate.ames/rxnbench/Gantry/v0"
    preferred_mdi_size = (960, 800)

    def __init__(
        self,
        server: DiscoveredServer,
        t: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._server = server
        self._t      = t
        self._homed  = False

        self._client = SilaClient()

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "gantry_widget.ui"))
        f.open(QFile.ReadOnly)
        self._ctrl = loader.load(f, None)
        f.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ctrl)

        self._find_children()
        self._inject_right_panel()
        self._apply_theme()
        self._fill_connection_bar()
        self._wire_client()
        self._wire_controls()

        self._client.connect_to(server.host, server.port)


    def _find_children(self) -> None:
        c = self._ctrl
        self._server_addr_lbl = c.findChild(QLabel,      "server_addr_lbl")
        self._conn_dot        = c.findChild(QLabel,      "conn_dot")
        self._conn_status    = c.findChild(QLabel,      "conn_status_lbl")
        self._machine_lbl    = c.findChild(QLabel,      "machine_state_lbl")
        if self._machine_lbl:
            self._machine_lbl.hide()
        self._x_lbl          = c.findChild(QLabel,      "x_lbl")
        self._y_lbl          = c.findChild(QLabel,      "y_lbl")
        self._z_lbl          = c.findChild(QLabel,      "z_lbl")
        self._homing_dot     = c.findChild(QLabel,      "homing_dot")
        self._homing_lbl     = c.findChild(QLabel,      "homing_status_lbl")
        self._last_homed_lbl = c.findChild(QLabel,      "last_homed_lbl")
        self._home_btn       = c.findChild(QPushButton, "open_homing_btn")
        self._right_panel    = c.findChild(QWidget,     "right_panel")
        # Slot 1
        self._th1_combo      = c.findChild(QComboBox,   "toolhead1_combo")
        self._th1_lbl        = c.findChild(QLabel,      "toolhead1_display_lbl")
        self._th1_mounted    = c.findChild(QLabel,      "toolhead1_mounted_lbl")
        self._th1_cal_lbl    = c.findChild(QLabel,      "slot1_last_cal_lbl")
        self._activate1_btn  = c.findChild(QPushButton, "activate_slot1_btn")
        self._confirm1_btn   = c.findChild(QPushButton, "confirm_mounted1_btn")
        self._clrmount1_btn  = c.findChild(QPushButton, "clear_mounted1_btn")
        self._clearth1_btn   = c.findChild(QPushButton, "clear_toolhead1_btn")
        self._cal1_btn       = c.findChild(QPushButton, "calibrate_slot1_btn")
        # Slot 2
        self._slot2_group    = c.findChild(QGroupBox,   "slot2_group")
        self._add_slot2_btn  = c.findChild(QPushButton, "add_slot2_btn")
        self._th2_combo      = c.findChild(QComboBox,   "toolhead2_combo")
        self._th2_lbl        = c.findChild(QLabel,      "toolhead2_display_lbl")
        self._th2_mounted    = c.findChild(QLabel,      "toolhead2_mounted_lbl")
        self._th2_cal_lbl    = c.findChild(QLabel,      "slot2_last_cal_lbl")
        self._activate2_btn  = c.findChild(QPushButton, "activate_slot2_btn")
        self._confirm2_btn   = c.findChild(QPushButton, "confirm_mounted2_btn")
        self._clrmount2_btn  = c.findChild(QPushButton, "clear_mounted2_btn")
        self._clearth2_btn   = c.findChild(QPushButton, "clear_toolhead2_btn")
        self._cal2_btn       = c.findChild(QPushButton, "calibrate_slot2_btn")

    def _inject_right_panel(self) -> None:
        """Fill the right_panel placeholder with the workspace loader."""
        self._workspace_widget = WorkspaceLoaderWidget(self._t, server=self._server)
        lay = QVBoxLayout(self._right_panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._workspace_widget)

    def _apply_theme(self) -> None:
        t = self._t
        self._ctrl.setStyleSheet(
            f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}"
            f"QGroupBox {{ color: {t['text']}; border: 1px solid {t['border']};"
            f" border-radius: 4px; margin-top: 8px; padding-top: 6px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {t['text_muted']}; }}"
            f"QLabel {{ color: {t['text']}; }}"
            f"QLineEdit {{ background: {t['bg']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 2px 6px; }}"
            f"QComboBox {{ background: {t['bg']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 2px 6px; }}"
            f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; padding: 4px 8px; }}"
            f"QPushButton:hover {{ border-color: {t['accent']}; }}"
        )
        if hasattr(self._workspace_widget, "set_theme"):
            self._workspace_widget.set_theme(t)

    def _fill_connection_bar(self) -> None:
        if self._server_addr_lbl:
            self._server_addr_lbl.setText(f"{self._server.host}:{self._server.port}")
            self._server_addr_lbl.setStyleSheet(
                f"color: {self._t['text_muted']}; font-size: 9pt;"
            )

    def _wire_client(self) -> None:
        c = self._client
        c.connection_changed.connect(self._on_connection)
        c.position_updated.connect(self._on_position)
        c.state_updated.connect(self._on_state)
        c.toolhead_updated.connect(self._on_toolhead)
        c.saved_state_updated.connect(self._on_saved_state)
        c.error_occurred.connect(self._on_error)

    def _wire_controls(self) -> None:
        if self._home_btn:
            self._home_btn.clicked.connect(self._open_homing)
        # Slot 1
        if self._activate1_btn:
            self._activate1_btn.clicked.connect(self._activate_slot1)
        if self._confirm1_btn:
            self._confirm1_btn.clicked.connect(self._client.confirm_toolhead_mounted)
        if self._clrmount1_btn:
            self._clrmount1_btn.clicked.connect(self._client.clear_toolhead_mounted)
        if self._clearth1_btn:
            self._clearth1_btn.clicked.connect(self._client.clear_toolhead)
        if self._cal1_btn:
            self._cal1_btn.clicked.connect(self._open_calibration)
        # Slot 2
        if self._add_slot2_btn:
            self._add_slot2_btn.clicked.connect(self._toggle_slot2)
        if self._activate2_btn:
            self._activate2_btn.clicked.connect(self._activate_slot2)
        if self._confirm2_btn:
            self._confirm2_btn.clicked.connect(self._client.confirm_toolhead_mounted)
        if self._clrmount2_btn:
            self._clrmount2_btn.clicked.connect(self._client.clear_toolhead_mounted)
        if self._clearth2_btn:
            self._clearth2_btn.clicked.connect(self._client.clear_toolhead)
        if self._cal2_btn:
            self._cal2_btn.clicked.connect(self._open_calibration)

    def _load_toolheads(self) -> None:
        w = _ToolheadListWorker(self._client)
        w.done.connect(self._on_toolheads_loaded)
        w.start()
        self._th_worker = w


    def _on_toolheads_loaded(self, toolheads: list[tuple[str, str]]) -> None:
        if not self._th1_combo:
            return
        self._th1_combo.clear()
        for name, display in toolheads:
            self._th1_combo.addItem(display or name, userData=name)

    def _toggle_slot2(self) -> None:
        if self._slot2_group:
            visible = not self._slot2_group.isVisible()
            self._slot2_group.setVisible(visible)
            if self._add_slot2_btn:
                self._add_slot2_btn.setText("− Multi-head" if visible else "+ Multi-head")

    def _activate_slot1(self) -> None:
        if self._th1_combo:
            name = self._th1_combo.currentData()
            if name:
                self._client.set_toolhead(name)

    def _activate_slot2(self) -> None:
        if self._th2_combo:
            name = self._th2_combo.currentData()
            if name:
                self._client.set_toolhead(name)


    def _open_homing(self) -> None:
        from .homing_dialog import HomingDialog
        dlg = HomingDialog(self._client, self._t, self)
        dlg.exec()

    def _open_calibration(self) -> None:
        from .toolhead_calibration_dialog import ToolheadCalibrationDialog
        name = ""
        if self._th1_combo and self._th1_combo.currentData():
            name = self._th1_combo.currentData()
        dlg = ToolheadCalibrationDialog(self._client, name, self._t, self)
        dlg.exec()


    def _on_connection(self, ready: bool) -> None:
        t = self._t
        col = t["dot_ok"] if ready else t["dot_err"]
        if self._conn_dot:
            self._conn_dot.setStyleSheet(f"color: {col};")
        if self._conn_status:
            self._conn_status.setText("Connected" if ready else "Disconnected")
        if ready:
            self._load_toolheads()

    def _on_position(self, x: float, y: float, z: float) -> None:
        if self._x_lbl: self._x_lbl.setText(f"X:   {x:8.2f}")
        if self._y_lbl: self._y_lbl.setText(f"Y:   {y:8.2f}")
        if self._z_lbl: self._z_lbl.setText(f"Z:   {z:8.2f}")

    def _on_state(self, state: str) -> None:
        if self._machine_lbl:
            self._machine_lbl.setText(state.capitalize())

    def _on_toolhead(self, info) -> None:
        if self._th1_lbl:
            self._th1_lbl.setText(info.display_name or info.name or "None selected")
        if self._th1_mounted:
            self._th1_mounted.setText("Mounted ✓" if info.toolhead_mounted else "Not mounted")
        if self._th1_cal_lbl:
            cal = getattr(info, "last_calibrated", None)
            self._th1_cal_lbl.setText(f"Last calibrated: {cal}" if cal else "Last calibrated: —")

    def _on_saved_state(self, has_state: bool) -> None:
        self._homed = has_state
        t = self._t
        col = t["dot_ok"] if has_state else t["dot_warn"]
        if self._homing_dot:
            self._homing_dot.setStyleSheet(f"color: {col};")
        if self._homing_lbl:
            self._homing_lbl.setText("Homed" if has_state else "Not homed")
        if self._last_homed_lbl:
            if has_state:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self._last_homed_lbl.setText(f"Last homed: {ts}")
            else:
                self._last_homed_lbl.setText("Last homed: —")

    def _on_error(self, msg: str) -> None:
        if self._conn_status:
            self._conn_status.setText(f"Error: {msg[:80]}")


    def set_theme(self, t: dict) -> None:
        self._t = t
        self._apply_theme()


    def closeEvent(self, event) -> None:  # noqa: N802
        self._client.disconnect()
        super().closeEvent(event)
