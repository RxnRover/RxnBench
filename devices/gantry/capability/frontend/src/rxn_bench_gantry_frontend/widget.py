"""Gantry control widget: connection bar, left sidebar (toolheads/homing/position), right workspace panel."""
from __future__ import annotations

import datetime
from functools import partial
from pathlib import Path

from PySide6.QtCore import QFile, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)
from PySide6.QtUiTools import QUiLoader

from rxn_bench_ui.discovery import DiscoveredServer
from .connection import GantryConnection
from .workspace_loader import DeckViewPanel, WorkspaceLoaderWidget

_UI_DIR = Path(__file__).parent / "ui"


class _ToolheadListWorker(QThread):
    done = Signal(list)  # list[tuple[str, str]]

    def __init__(self, client: GantryConnection) -> None:
        super().__init__()
        self._client = client

    def run(self) -> None:
        self.done.emit(self._client.fetch_toolhead_list())



class _LivePanel(QWidget):
    """Live status panel: current action, last well, and a workspace canvas with position overlay."""

    def __init__(self, t: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = t

        self._action_lbl = QLabel("Standby")
        self._well_lbl   = QLabel("-")
        self._canvas     = DeckViewPanel(t)
        self._details_chk = QCheckBox("Show more details")
        self._details_chk.setToolTip(
            "Show the deck's axis-limit boundary and corner coordinates on the canvas"
        )
        self._details_chk.toggled.connect(self._canvas.set_show_details)

        # Status strip
        strip = QWidget()
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(6, 4, 6, 4)
        strip_lay.setSpacing(12)

        action_head = QLabel("Action")
        well_head   = QLabel("Well")
        for lbl in (action_head, well_head):
            f = lbl.font()
            f.setBold(True)
            lbl.setFont(f)

        strip_lay.addWidget(action_head)
        strip_lay.addWidget(self._action_lbl, 2)
        strip_lay.addWidget(well_head)
        strip_lay.addWidget(self._well_lbl, 1)
        strip_lay.addWidget(self._details_chk)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(strip)
        lay.addWidget(self._canvas, 1)

        self._apply_style()

    def _apply_style(self) -> None:
        t = self._t
        self.setStyleSheet(
            f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}"
            f"QLabel   {{ background: transparent; }}"
        )

    def set_action(self, text: str) -> None:
        self._action_lbl.setText(text)
        if text.startswith("Error:"):
            self._action_lbl.setStyleSheet("color: #e05252; font-weight: bold;")
        else:
            self._action_lbl.setStyleSheet("")

    def set_well(self, label: str) -> None:
        self._well_lbl.setText(label or "-")
        # Highlight the well on canvas
        if "/" in label:
            plate_id, well = label.split("/", 1)
        elif label and label != "-":
            plate_id, well = "", label
        else:
            plate_id, well = "", ""
        self._canvas.set_active_well(plate_id, well)

    def set_position(self, x: float, y: float, z: float) -> None:
        self._canvas.set_current_position(x, y, z)

    def set_plate_specs(self, labware: dict) -> None:
        self._canvas.set_plate_specs(labware)

    def set_limits(
        self,
        x_min: float, x_max: float, y_min: float, y_max: float,
        z_min: float, z_max: float, safe_clearance_z: float,
        crossbar_clearance_above_tip: float | None = None,
        crossbar_y_thickness: float | None = None,
    ) -> None:
        self._canvas.set_limits(
            x_min, x_max, y_min, y_max, z_min, z_max, safe_clearance_z,
            crossbar_clearance_above_tip, crossbar_y_thickness,
        )

    def set_toolhead_z_engage(self, value: float | None) -> None:
        self._canvas.set_toolhead_z_engage(value)

    def load_workspace(self, ws: dict) -> None:
        self._canvas.load(ws)

    def set_theme(self, t: dict) -> None:
        self._t = t
        self._canvas.set_theme(t)
        self._apply_style()


class GantryWidget(QWidget):
    """MDI sub-window for the gantry device: jog controls, toolhead selector, and workspace loader."""

    FEATURE_ID = "edu.iastate.ames/rxnbench/Gantry/v1"
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
        self._locked = False                 # experiment lock held by a script
        self._last_th_info = None            # latest ToolheadInfo from the stream

        self._client     = GantryConnection()
        self._live_panel: _LivePanel | None = None
        self._th_worker: _ToolheadListWorker | None = None

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
        self._slot1_active   = c.findChild(QLabel,      "slot1_active_lbl")
        self._slot1_last_cal = c.findChild(QLabel,      "slot1_last_cal_lbl")
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
        self._slot2_active   = c.findChild(QLabel,      "slot2_active_lbl")
        self._slot2_last_cal = c.findChild(QLabel,      "slot2_last_cal_lbl")
        self._activate2_btn  = c.findChild(QPushButton, "activate_slot2_btn")
        self._confirm2_btn   = c.findChild(QPushButton, "confirm_mounted2_btn")
        self._clrmount2_btn  = c.findChild(QPushButton, "clear_mounted2_btn")
        self._clearth2_btn   = c.findChild(QPushButton, "clear_toolhead2_btn")
        self._cal2_btn       = c.findChild(QPushButton, "calibrate_slot2_btn")

    def _inject_right_panel(self) -> None:
        self._workspace_widget = WorkspaceLoaderWidget(self._t, client=self._client)
        self._workspace_widget.workspace_changed.connect(self._on_workspace_changed)

        self._live_panel = _LivePanel(self._t)

        # Experiment running banner (hidden until an experiment acquires the lock)
        self._exp_banner = QWidget()
        exp_lay = QHBoxLayout(self._exp_banner)
        exp_lay.setContentsMargins(8, 6, 8, 6)
        self._exp_lbl = QLabel("Experiment running - manual controls disabled")
        self._exp_pause_btn  = QPushButton("Pause")
        self._exp_resume_btn = QPushButton("Resume")
        self._exp_stop_btn   = QPushButton("Stop")
        self._exp_force_btn  = QPushButton("Force release")
        self._exp_force_btn.setToolTip(
            "Recovery only: forcibly release the experiment lock when the\n"
            "controlling script died without releasing it (killed process)."
        )
        self._exp_resume_btn.hide()
        exp_lay.addWidget(self._exp_lbl, 1)
        exp_lay.addWidget(self._exp_pause_btn)
        exp_lay.addWidget(self._exp_resume_btn)
        exp_lay.addWidget(self._exp_stop_btn)
        exp_lay.addWidget(self._exp_force_btn)
        self._exp_banner.hide()
        self._exp_banner.setStyleSheet(
            "QWidget { background: #7c5200; color: #ffe0a0; border-radius: 4px; }"
            "QPushButton { background: #a06800; color: #ffe0a0;"
            " border: 1px solid #c48200; border-radius: 3px; padding: 3px 10px; }"
            "QPushButton:hover { background: #c48200; }"
        )

        self._exp_pause_btn.clicked.connect(self._on_exp_pause)
        self._exp_resume_btn.clicked.connect(self._on_exp_resume)
        self._exp_stop_btn.clicked.connect(self._client.stop_experiment)
        self._exp_force_btn.clicked.connect(self._on_exp_force_release)

        tabs = QTabWidget()
        tabs.addTab(self._live_panel,        "Live")
        tabs.addTab(self._workspace_widget,  "Configuration")

        lay = QVBoxLayout(self._right_panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._exp_banner)
        lay.addWidget(tabs)

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
        c.position_updated.connect(self._on_position_live)
        c.well_changed.connect(self._on_well_changed)
        c.action_changed.connect(self._on_action_changed)
        c.workspace_yaml_changed.connect(self._on_workspace_yaml_changed)
        c.experiment_active_changed.connect(self._on_experiment_active)
        c.labware_updated.connect(self._on_labware)
        c.limits_updated.connect(self._on_limits)

    def _wire_controls(self) -> None:
        if self._home_btn:
            self._home_btn.clicked.connect(self._open_homing)
        # Per-slot mount/remove buttons act on the *active* toolhead, so
        # _refresh_slots only enables them on the slot that is active.
        for combo, activate_btn in (
            (self._th1_combo, self._activate1_btn),
            (self._th2_combo, self._activate2_btn),
        ):
            if activate_btn:
                activate_btn.clicked.connect(partial(self._activate_slot, combo))
            if combo:
                combo.currentIndexChanged.connect(lambda _i: self._refresh_slots())
        for btn in (self._confirm1_btn, self._confirm2_btn):
            if btn:
                # clicked emits a bool - connecting directly would pass it as
                # confirm_toolhead_mounted's token: str param, and protobuf's
                # strict string typing raises TypeError on every click. The
                # button appears completely dead (no crash, no error shown).
                btn.clicked.connect(lambda: self._client.confirm_toolhead_mounted())
        for btn in (self._clrmount1_btn, self._clrmount2_btn):
            if btn:
                btn.clicked.connect(lambda: self._client.clear_toolhead_mounted())
        for btn in (self._clearth1_btn, self._clearth2_btn):
            if btn:
                btn.clicked.connect(self._client.clear_toolhead)
        for btn in (self._cal1_btn, self._cal2_btn):
            if btn:
                btn.clicked.connect(self._open_calibration)
        if self._add_slot2_btn:
            self._add_slot2_btn.clicked.connect(self._toggle_slot2)

    def _load_toolheads(self) -> None:
        if self._th_worker is not None and self._th_worker.isRunning():
            return  # a fetch is already in flight; it will deliver fresh data
        w = _ToolheadListWorker(self._client)
        w.done.connect(self._on_toolheads_loaded)
        w.start()
        self._th_worker = w

    def _on_toolheads_loaded(self, toolheads: list[tuple[str, str]]) -> None:
        for combo in (self._th1_combo, self._th2_combo):
            if not combo:
                continue
            selected = combo.currentData()
            combo.clear()
            for name, display in toolheads:
                combo.addItem(display or name, userData=name)
            if selected:
                idx = combo.findData(selected)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        self._refresh_slots()

    def _toggle_slot2(self) -> None:
        if self._slot2_group:
            visible = not self._slot2_group.isVisible()
            self._slot2_group.setVisible(visible)
            if self._add_slot2_btn:
                self._add_slot2_btn.setText("− Multi-head" if visible else "+ Multi-head")

    def _activate_slot(self, combo: QComboBox | None) -> None:
        """Switch the active toolhead to this slot's selection."""
        if combo:
            name = combo.currentData()
            if name:
                self._set_action(f"Activating {combo.currentText()}")
                self._client.set_toolhead(name)


    def _open_homing(self) -> None:
        self._set_action("Manual Homing")
        from .homing_dialog import HomingDialog
        dlg = HomingDialog(self._client, self._t, self)
        dlg.exec()
        self._set_action("Standby")

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

    def _on_position_live(self, x: float, y: float, z: float) -> None:
        if self._live_panel:
            self._live_panel.set_position(x, y, z)

    def _on_workspace_changed(self, ws: dict) -> None:
        if self._live_panel:
            self._live_panel.load_workspace(ws)

    def _set_action(self, text: str) -> None:
        if self._live_panel:
            self._live_panel.set_action(text)

    def _on_state(self, state: str) -> None:
        if self._machine_lbl:
            self._machine_lbl.setText(state.capitalize())

    def _on_action_changed(self, action: str) -> None:
        if self._live_panel:
            self._live_panel.set_action(action)

    def _on_well_changed(self, label: str) -> None:
        if self._live_panel:
            self._live_panel.set_well(label)

    def _on_workspace_yaml_changed(self, yaml_text: str) -> None:
        if not yaml_text or not self._live_panel:
            return
        import yaml as _yaml
        try:
            ws = _yaml.safe_load(yaml_text)
            if isinstance(ws, dict) and "plates" in ws:
                self._live_panel.load_workspace(ws)
        except Exception:
            pass

    def _on_toolhead(self, info) -> None:
        self._last_th_info = info
        self._refresh_slots()
        if self._live_panel:
            self._live_panel.set_toolhead_z_engage(info.z_engage if info.active else None)

    def _on_labware(self, labware: dict) -> None:
        """Server-sourced plate geometry: forward to both deck canvases."""
        if self._live_panel:
            self._live_panel.set_plate_specs(labware)
        if hasattr(self, "_workspace_widget"):
            self._workspace_widget._canvas.set_plate_specs(labware)

    def _on_limits(
        self, x_min: float, x_max: float, y_min: float, y_max: float,
        z_min: float, z_max: float, safe_clearance_z: float,
        crossbar_clearance_above_tip: float | None = None,
        crossbar_y_thickness: float | None = None,
    ) -> None:
        """Server-sourced axis limits + safe clearance + crossbar geometry: forward to the Live tab's canvas.

        The Configuration tab's canvas connects to limits_updated directly
        (see WorkspaceLoaderWidget.__init__) since it owns its own client
        reference; this handler only covers the Live tab's separate canvas
        instance.
        """
        if self._live_panel:
            self._live_panel.set_limits(
                x_min, x_max, y_min, y_max, z_min, z_max, safe_clearance_z,
                crossbar_clearance_above_tip, crossbar_y_thickness,
            )

    def _slot_widgets(self):
        """Yield (combo, display_lbl, mounted_lbl, active_lbl, last_cal_lbl, per-slot buttons) per slot."""
        return (
            (self._th1_combo, self._th1_lbl, self._th1_mounted, self._slot1_active, self._slot1_last_cal,
             (self._confirm1_btn, self._clrmount1_btn, self._clearth1_btn, self._cal1_btn)),
            (self._th2_combo, self._th2_lbl, self._th2_mounted, self._slot2_active, self._slot2_last_cal,
             (self._confirm2_btn, self._clrmount2_btn, self._clearth2_btn, self._cal2_btn)),
        )

    @staticmethod
    def _format_calibrated_at(iso_ts: str) -> str:
        try:
            return datetime.datetime.fromisoformat(iso_ts).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return iso_ts

    def _refresh_slots(self) -> None:
        """Reflect the server's toolhead state onto both slots.

        One toolhead is *active* at a time, but several can be physically
        mounted at once - mount confirmations are per-head and survive
        activation switches. A slot is "active" when its combo selection
        matches the server's active toolhead (slot 1 wins a tie, and hosts the
        active head if no slot's selection matches, e.g. state restored at
        boot). Each slot's mounted label reflects its own selected head's
        confirmation, so both heads' readiness is visible before a script runs.
        Mount/remove/calibrate act on the active toolhead, so those buttons are
        only enabled on the active slot.
        """
        info = self._last_th_info
        slots = self._slot_widgets()
        mounted_names = set(info.mounted_toolheads) if info is not None else set()

        active_idx = -1
        if info is not None and info.active:
            for i, (combo, *_rest) in enumerate(slots):
                if combo and combo.currentData() == info.name:
                    active_idx = i
                    break
            if active_idx < 0:
                active_idx = 0  # active head not selected in any slot: show on slot 1

        for i, (combo, lbl, mounted_lbl, active_lbl, last_cal_lbl, buttons) in enumerate(slots):
            is_active = i == active_idx
            selected = combo.currentData() if combo else None
            if active_lbl:
                active_lbl.setVisible(is_active)
                if is_active:
                    # Without an explicit color the "ACTIVE" label just inherits
                    # the widget's default text color (looks black/off, not
                    # like a status indicator at all).
                    active_lbl.setStyleSheet(f"color: {self._t['dot_ok']}; font-weight: bold;")
            if lbl:
                if is_active:
                    lbl.setText(info.display_name or info.name)
                else:
                    lbl.setText(combo.currentText() if selected else "None selected")
            if mounted_lbl:
                shown = info.name if is_active and info is not None else selected
                if shown:
                    mounted_lbl.setText("Mounted ✓" if shown in mounted_names else "Not mounted")
                else:
                    mounted_lbl.setText("-")
            if last_cal_lbl:
                # Calibration timestamp is only known for the *active* toolhead
                # (ToolheadInfo describes whichever head is active, not every
                # configured one) - a non-active slot's selection can't be
                # shown without a bulk-fetch RPC that doesn't exist yet.
                if is_active and info is not None and info.calibrated_at:
                    last_cal_lbl.setText(f"Last calibrated: {self._format_calibrated_at(info.calibrated_at)}")
                elif is_active:
                    last_cal_lbl.setText("Last calibrated: never")
                else:
                    last_cal_lbl.setText("Last calibrated: -")
            for btn in buttons:
                if btn:
                    btn.setEnabled(is_active and not self._locked)
            if combo:
                combo.setEnabled(not self._locked)

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
                self._last_homed_lbl.setText("Last homed: -")

    def _on_experiment_active(self, active: bool) -> None:
        self._exp_banner.setVisible(active)
        self._set_controls_locked(active)
        if not active:
            self._exp_pause_btn.show()
            self._exp_resume_btn.hide()

    def _on_exp_pause(self) -> None:
        self._client.pause_experiment()
        self._exp_lbl.setText("Experiment paused")
        self._exp_pause_btn.hide()
        self._exp_resume_btn.show()

    def _on_exp_resume(self) -> None:
        self._client.resume_experiment()
        self._exp_lbl.setText("Experiment running - manual controls disabled")
        self._exp_pause_btn.show()
        self._exp_resume_btn.hide()

    def _on_exp_force_release(self) -> None:
        """Tokenless lock recovery for when the controlling script died."""
        from PySide6.QtWidgets import QMessageBox
        answer = QMessageBox.warning(
            self, "Force-release experiment lock",
            "Force-release the experiment lock?\n\n"
            "Only do this if the controlling script has crashed or was killed. "
            "If a script is still running, it will lose its exclusive control "
            "of the gantry.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self._client.force_release_experiment_lock()

    def _set_controls_locked(self, locked: bool) -> None:
        """Disable/enable all manual controls while an experiment holds the lock."""
        self._locked = locked
        for btn in (
            self._home_btn,
            self._activate1_btn, self._activate2_btn,
            self._add_slot2_btn,
        ):
            if btn:
                btn.setEnabled(not locked)
        # Per-slot mount/remove/calibrate buttons and combos are managed by
        # _refresh_slots (their enabled state also depends on the active slot).
        self._refresh_slots()

    def _on_error(self, msg: str) -> None:
        """Surface command/stream errors in the Live tab action label."""
        self._set_action(f"Error: {msg}")


    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and propagate it to the live panel and workspace widget."""
        self._t = t
        self._apply_theme()
        if self._live_panel:
            self._live_panel.set_theme(t)
        if hasattr(self, "_workspace_widget") and hasattr(self._workspace_widget, "set_theme"):
            self._workspace_widget.set_theme(t)


    def closeEvent(self, event) -> None:  # noqa: N802
        """Disconnect the gRPC client when the sub-window is closed."""
        self._client.close()
        super().closeEvent(event)
