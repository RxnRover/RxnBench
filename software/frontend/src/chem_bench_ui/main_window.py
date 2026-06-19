from PySide6.QtCore import Qt, QTimer, QEvent, QSettings
from PySide6.QtGui import QColor, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QGroupBox, QTabWidget, QMessageBox,
)

from chem_bench_ui.sila_client import SilaClient, ToolheadInfo
from chem_bench_ui.themes import get as _get_theme, build_qss as _build_qss
from chem_bench_ui.widgets.position_grid import PositionGrid
from chem_bench_ui.widgets.zbar import ZBar
from chem_bench_ui.widgets.toolhead_diagram import ToolheadDiagramWidget
from chem_bench_ui.widgets.toolhead_panel import ToolheadPanel, ToolheadManagerPanel
from chem_bench_ui.widgets.server_panel import ServerInfoPanel
from chem_bench_ui.widgets.homing_panel import HomingPanel
from chem_bench_ui.widgets.jog_panel import JogPanel


class MainWindow(QMainWindow):
    """
    Top-level window.

    Connection bar (always visible at top — SiLA server dot)
    ──────────────────────────────────────────────────────────
    QTabWidget  (starts with only "Server" tab; feature tabs injected dynamically
                 after _discover_and_stream() probes the server)
      ├─ "Motion Platform"  added when feature found, has its own ● dot
      ├─ "Toolheads"        added alongside Motion Platform
      └─ "Server"           always present; shows SiLA + per-feature status
    ──────────────────────────────────────────────────────────
    Error toast
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chem Bench Control")
        self.setMinimumSize(960, 600)

        self._settings = QSettings("ChemBench", "ChemBenchUI")
        self._theme_name: str = self._settings.value("theme", "dark")
        self._dev_mode: bool = self._settings.value("dev_mode", True, type=bool)

        self._client = SilaClient()
        self._homed = False
        self._current_z = 0.0

        # Feature tab widgets are built once then inserted/removed from tab widget
        self._motion_widget: QWidget | None = None
        self._toolhead_mgr: ToolheadManagerPanel | None = None
        self._motion_dot: QLabel | None = None
        self._shown_features: set[str] = set()

        self._build_ui()
        self._build_menu()

        # Always-on signals
        self._client.connection_changed.connect(self._on_connected)
        self._client.error_occurred.connect(self._show_error)
        self._client.features_discovered.connect(self._on_features_discovered)
        self._client.feature_state_changed.connect(self._on_feature_state)
        self._client.saved_state_updated.connect(self._on_saved_state)

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)

        self._server_panel.update_host("localhost")
        self._client.connect_to("localhost")

        QApplication.instance().installEventFilter(self)

    # ── Theme + menu ──────────────────────────────────────────────────────────

    def _apply_theme(self):
        t = _get_theme(self._theme_name)
        self.setStyleSheet(_build_qss(t))
        # Push theme to paintEvent-based widgets (QSS doesn't reach them)
        if hasattr(self, '_grid'):
            self._grid.set_theme(t)
        if hasattr(self, '_zbar'):
            self._zbar.set_theme(t)
        if hasattr(self, '_toolhead_mgr'):
            self._toolhead_mgr.set_theme(t)
        # Refresh motion status bar (hardcoded style must follow theme)
        if hasattr(self, '_motion_status_bar'):
            self._motion_status_bar.setStyleSheet(
                f"background:{t['bg_surface']}; border-bottom:1px solid {t['border']};"
            )

    def _set_theme(self, name: str):
        self._theme_name = name
        self._settings.setValue("theme", name)
        self._apply_theme()

    def _build_menu(self):
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu("File")
        self._save_park_action = QAction("Save && Quit", self)
        self._save_park_action.setToolTip("Park toolhead, save homing state, then exit")
        self._save_park_action.triggered.connect(self._save_and_quit)
        self._save_park_action.setEnabled(False)
        file_menu.addAction(self._save_park_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = mb.addMenu("View")

        dark_action = QAction("Dark Theme", self)
        dark_action.setCheckable(True)
        dark_action.setChecked(self._theme_name == "dark")
        dark_action.triggered.connect(lambda: self._set_theme("dark"))

        light_action = QAction("Light Theme", self)
        light_action.setCheckable(True)
        light_action.setChecked(self._theme_name == "light")
        light_action.triggered.connect(lambda: self._set_theme("light"))

        # Keep the two theme actions mutually exclusive
        dark_action.triggered.connect(lambda: light_action.setChecked(False))
        light_action.triggered.connect(lambda: dark_action.setChecked(False))

        view_menu.addAction(dark_action)
        view_menu.addAction(light_action)
        view_menu.addSeparator()

        self._dev_mode_action = QAction("Developer Mode", self)
        self._dev_mode_action.setCheckable(True)
        self._dev_mode_action.setChecked(self._dev_mode)
        self._dev_mode_action.triggered.connect(self._toggle_dev_mode)
        view_menu.addAction(self._dev_mode_action)

    def _toggle_dev_mode(self):
        entering_dev = self._dev_mode_action.isChecked()
        if entering_dev and not self._dev_mode:
            reply = QMessageBox.warning(
                self,
                "Enter Developer Mode",
                "You are entering Developer Mode.\n\n"
                "Direct motion commands and manual jog controls will be enabled. "
                "Incorrect use can result in unpredictable and potentially dangerous "
                "device behavior, including collisions.\n\n"
                "Only proceed if you understand the risks.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                self._dev_mode_action.setChecked(False)
                return
        self._dev_mode = entering_dev
        self._settings.setValue("dev_mode", self._dev_mode)
        self._refresh_mode_gates()

    def _refresh_mode_gates(self):
        """Enable or disable UI elements based on the current dev/user mode."""
        # Grid click-to-move only in dev mode
        if hasattr(self, '_grid'):
            self._grid.set_click_enabled(self._dev_mode)
        # Jog panel always available in dev mode; in user mode requires toolhead mounted
        if hasattr(self, '_jog') and self._jog is not None:
            self._jog.set_dev_mode(self._dev_mode)
        # Mode label in connection bar
        if hasattr(self, '_mode_lbl'):
            self._mode_lbl.setText("DEV" if self._dev_mode else "USER")
            t = _get_theme(self._theme_name)
            self._mode_lbl.setStyleSheet(
                f"color:{t['accent']}; font-size:10px; font-weight:bold; padding:2px 6px;"
                f"border:1px solid {t['accent']}; border-radius:3px;"
                if self._dev_mode else
                f"color:{t['accent2']}; font-size:10px; font-weight:bold; padding:2px 6px;"
                f"border:1px solid {t['accent2']}; border-radius:3px;"
            )

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # SiLA server connection bar (top, always visible)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("SiLA server:"))
        self._host_input = QLineEdit("localhost")
        self._host_input.setMaximumWidth(200)
        self._host_input.returnPressed.connect(self._reconnect)
        bar.addWidget(self._host_input)
        conn_btn = QPushButton("Connect")
        conn_btn.setMaximumWidth(80)
        conn_btn.clicked.connect(self._reconnect)
        bar.addWidget(conn_btn)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#f44336; font-size:16px;")
        bar.addWidget(self._dot)
        self._status_lbl = QLabel("Connecting…")
        self._status_lbl.setStyleSheet("color:#666;")
        bar.addWidget(self._status_lbl)
        bar.addStretch()
        self._mode_lbl = QLabel("DEV")
        bar.addWidget(self._mode_lbl)
        root.addLayout(bar)

        # Restore-homing banner (hidden until server confirms saved state)
        self._restore_banner = QLabel()
        self._restore_banner.setWordWrap(True)
        self._restore_banner.setVisible(False)
        self._restore_banner.setStyleSheet(
            "background:#1e3a5f; color:#93c5fd;"
            "border:1px solid #3b82f6; border-radius:4px;"
            "padding:4px 10px; font-size:11px;"
        )
        root.addWidget(self._restore_banner)

        # Tab widget — only Toolheads + Server tabs to start
        self._tabs = QTabWidget()
        diagram = ToolheadDiagramWidget()
        diagram.setFixedHeight(200)
        self._toolhead_mgr = ToolheadManagerPanel(diagram=diagram)
        self._tabs.addTab(self._toolhead_mgr, "Toolheads")
        self._server_panel = ServerInfoPanel()
        self._tabs.addTab(self._server_panel, "Server")
        root.addWidget(self._tabs, 1)

        # Error bar — always occupies a fixed slot so the tab widget never reclaims the space.
        # Content and style change rather than visibility toggling.
        self._toast = QLabel()
        self._toast.setWordWrap(True)
        self._toast.setFixedHeight(30)
        self._toast.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._toast.setStyleSheet("background:transparent; color:transparent; font-size:11px; padding:0 4px;")
        root.addWidget(self._toast)

        self._apply_theme()
        self._refresh_mode_gates()

    def _build_motion_tab(self) -> QWidget:
        """Build the Motion Platform tab content (called once on first discovery)."""
        wrapper = QWidget()
        vbox = QVBoxLayout(wrapper)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Per-feature connection status bar at the very top of the tab
        status_bar = QWidget()
        self._motion_status_bar = status_bar
        status_bar.setFixedHeight(28)
        t = _get_theme(self._theme_name)
        status_bar.setStyleSheet(
            f"background:{t['bg_surface']}; border-bottom:1px solid {t['border']};"
        )
        sb = QHBoxLayout(status_bar)
        sb.setContentsMargins(10, 0, 10, 0)
        self._motion_dot = QLabel("●")
        self._motion_dot.setStyleSheet("color:#ff9800; font-size:13px;")
        sb.addWidget(self._motion_dot)
        self._motion_feat_lbl = QLabel("Motion Platform  —  waiting for hardware…")
        self._motion_feat_lbl.setStyleSheet("color:#888; font-size:11px;")
        sb.addWidget(self._motion_feat_lbl)
        sb.addStretch()
        vbox.addWidget(status_bar)

        # Main content
        content_widget = QWidget()
        content = QHBoxLayout(content_widget)
        content.setSpacing(8)
        content.setContentsMargins(4, 4, 4, 4)

        # Left column
        left = QVBoxLayout()
        left.setSpacing(6)

        pos_box = QGroupBox("Status")
        pl = QVBoxLayout(pos_box)
        pl.setSpacing(4)
        self._state_lbl = QLabel("State: ---")
        self._state_lbl.setStyleSheet("font-family:monospace; font-size:13px;")
        pl.addWidget(self._state_lbl)

        self._more_btn = QPushButton("Show position ▾")
        self._more_btn.setFlat(True)
        self._more_btn.setStyleSheet(
            "color:#555; font-size:10px; text-align:left; border:none; padding:0;"
        )
        self._more_btn.clicked.connect(self._toggle_position)
        pl.addWidget(self._more_btn)

        self._pos_detail = QWidget()
        dl = QVBoxLayout(self._pos_detail)
        dl.setContentsMargins(0, 2, 0, 0)
        dl.setSpacing(1)
        self._x_lbl = QLabel("X:  ---")
        self._y_lbl = QLabel("Y:  ---")
        self._z_lbl = QLabel("Z:  ---")
        for lbl in (self._x_lbl, self._y_lbl, self._z_lbl):
            lbl.setStyleSheet("font-family:monospace; font-size:12px; color:#888;")
            dl.addWidget(lbl)
        self._pos_detail.setVisible(False)
        pl.addWidget(self._pos_detail)
        left.addWidget(pos_box)

        self._toolhead_panel = ToolheadPanel(self._client)
        left.addWidget(self._toolhead_panel)
        self._homing = HomingPanel(self._client)
        left.addWidget(self._homing)
        left.addStretch()
        content.addLayout(left)

        # Right column
        right = QVBoxLayout()
        grid_row = QHBoxLayout()
        grid_row.setSpacing(4)
        self._grid = PositionGrid()
        grid_row.addWidget(self._grid, 1)
        self._zbar = ZBar()
        grid_row.addWidget(self._zbar)
        right.addLayout(grid_row, 1)
        self._jog = JogPanel(self._client)
        right.addWidget(self._jog)
        content.addLayout(right, 1)

        vbox.addWidget(content_widget, 1)
        return wrapper

    # ── Dynamic feature tab management ────────────────────────────────────

    def _on_features_discovered(self, features: list[str]):
        """Insert tabs for newly found features; update server panel."""
        new = set(features) - self._shown_features

        if "Motion Platform" in new:
            if self._motion_widget is None:
                # First time: build motion widgets and wire up signals
                self._motion_widget = self._build_motion_tab()
                self._grid.move_requested.connect(self._on_grid_click)
                self._client.position_updated.connect(self._on_position)
                self._client.state_updated.connect(self._on_state)
                self._client.toolhead_updated.connect(self._on_toolhead)

            # Always refresh — covers first load AND reconnect
            self._toolhead_panel.update_client(self._client)
            self._toolhead_mgr.connect_client(self._client)
            self._homing.update_client(self._client)
            self._jog.update_client(self._client)

            # Insert Motion Platform tab before the Toolheads tab (Toolheads is always present)
            toolheads_idx = self._tabs.indexOf(self._toolhead_mgr)
            self._tabs.insertTab(toolheads_idx, self._motion_widget, "Motion Platform")
            self._tabs.setCurrentIndex(0)
            self._shown_features.add("Motion Platform")
            # Apply mode gates now that jog panel and grid exist
            self._refresh_mode_gates()
            self._apply_theme()

        # Remove tabs for features no longer present
        gone = self._shown_features - set(features)
        if "Motion Platform" in gone and self._motion_widget is not None:
            self._tabs.removeTab(self._tabs.indexOf(self._motion_widget))
            self._toolhead_mgr.disconnect_client()
            self._shown_features.discard("Motion Platform")

        self._server_panel.update_features(features)

    def _on_feature_state(self, feature: str, ok: bool):
        """Update the per-feature ● indicator inside the feature's tab."""
        t = _get_theme(self._theme_name)
        if feature == "Motion Platform" and self._motion_dot is not None:
            self._motion_dot.setStyleSheet(
                f"color:{t['dot_ok'] if ok else t['dot_warn']}; font-size:13px;"
            )
            self._motion_feat_lbl.setText(
                "Motion Platform  —  hardware connected" if ok
                else "Motion Platform  —  waiting for hardware…"
            )
        self._server_panel.update_feature_stream(feature, ok)

    # ── General slots ──────────────────────────────────────────────────────

    def _reconnect(self):
        host = self._host_input.text().strip()
        if not host:
            return
        self._server_panel.update_host(host)
        # Remove Motion Platform tab so it's re-added cleanly after re-discovery
        # (Toolheads tab stays — it's always present)
        if self._motion_widget and self._tabs.indexOf(self._motion_widget) >= 0:
            self._tabs.removeTab(self._tabs.indexOf(self._motion_widget))
        self._shown_features.clear()
        self._client.connect_to(host)

    def _show_error(self, msg: str):
        self._toast.setText(f"⚠  {msg}")
        self._toast.setStyleSheet(
            "background:#7f1d1d; color:#fca5a5;"
            "border:1px solid #ef4444; border-radius:4px;"
            "padding:0 10px; font-size:11px;"
        )
        self._toast_timer.start(8000)

    def _clear_toast(self):
        self._toast.setText("")
        self._toast.setStyleSheet("background:transparent; color:transparent; font-size:11px; padding:0 4px;")

    def _on_saved_state(self, has_state: bool):
        self._save_park_action.setEnabled(True)
        if has_state:
            self._restore_banner.setText(
                "⚠  Homing restored from previous session — verify position before running experiments."
            )
            self._restore_banner.setVisible(True)
        else:
            self._restore_banner.setVisible(False)

    def _save_and_quit(self):
        reply = QMessageBox.question(
            self, "Save & Quit",
            "Park the toolhead and save homing state, then close?\n\n"
            "Next session will restore limits automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._client.save_and_park()
            self.close()

    def _toggle_position(self):
        visible = not self._pos_detail.isVisible()
        self._pos_detail.setVisible(visible)
        self._more_btn.setText("Hide position ▴" if visible else "Show position ▾")

    def _on_position(self, x, y, z):
        self._x_lbl.setText(f"X:  {x:8.2f} mm")
        self._y_lbl.setText(f"Y:  {y:8.2f} mm")
        self._z_lbl.setText(f"Z:  {z:8.2f} mm")
        self._current_z = z
        self._grid.set_position(x, y, self._homed)
        self._zbar.set_z(z, self._homed)

    def _on_toolhead(self, info: ToolheadInfo):
        self._toolhead_panel.update_info(info)
        self._toolhead_mgr.update_info(info)
        self._grid.set_toolhead(info if info.active else None)
        self._zbar.set_toolhead(info if info.active else None)

    def _on_grid_click(self, x: float, y: float):
        self._client.move_to(x, y, self._current_z)

    def _on_state(self, state: str):
        self._state_lbl.setText(state)
        self._homed = state.lower() == "ready"

    def _on_connected(self, ok: bool):
        t = _get_theme(self._theme_name)
        color = t['dot_ok'] if ok else t['dot_err']
        self._dot.setStyleSheet(f"color:{color}; font-size:16px;")
        self._status_lbl.setText(
            f"Connected — {self._client._host}" if ok
            else "Not connected — retrying…"
        )
        self._server_panel.update_connection(ok)
        if not ok:
            self._save_park_action.setEnabled(False)
            self._restore_banner.setVisible(False)
            self._toolhead_mgr.disconnect_client()

    # ── Key event filter ───────────────────────────────────────────────────

    _JOG_KEYS = {
        Qt.Key.Key_Left, Qt.Key.Key_Right,
        Qt.Key.Key_Up, Qt.Key.Key_Down,
        Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
    }

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in self._JOG_KEYS
            and not self._host_input.hasFocus()
            and self._motion_widget is not None
        ):
            self._jog.handle_key(event.key())
            return True
        return super().eventFilter(obj, event)
