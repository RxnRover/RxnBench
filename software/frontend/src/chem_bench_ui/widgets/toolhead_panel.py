import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QGridLayout,
)

from chem_bench_ui.sila_client import SilaClient, ToolheadInfo


class ToolheadPanel(QGroupBox):
    """Shows the active toolhead; dropdown populated from the server's installed configs."""

    _list_ready = Signal(list)   # emitted from bg thread → _populate on main thread

    def __init__(self, client: SilaClient):
        super().__init__("Toolhead")
        self._client = client
        self._names: list[str] = []   # parallel to combo items
        self._build()
        self._list_ready.connect(self._populate)

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(4)

        self._active_lbl = QLabel("None")
        self._active_lbl.setStyleSheet("font-size:11px; color:#555;")
        vbox.addWidget(self._active_lbl)

        # Dropdown + refresh
        row1 = QHBoxLayout()
        self._combo = QComboBox()
        self._combo.setPlaceholderText("select toolhead…")
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        row1.addWidget(self._combo, 1)
        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Refresh toolhead list from server")
        self._refresh_btn.clicked.connect(self._refresh)
        row1.addWidget(self._refresh_btn)
        vbox.addLayout(row1)

        # Set / Clear
        row2 = QHBoxLayout()
        set_btn = QPushButton("Set")
        set_btn.setStyleSheet("background:#1565c0; color:white; font-size:11px;")
        set_btn.clicked.connect(self._set)
        row2.addWidget(set_btn)
        clr_btn = QPushButton("Clear")
        clr_btn.setStyleSheet("color:#666; font-size:11px;")
        clr_btn.clicked.connect(self._clear)
        row2.addWidget(clr_btn)
        vbox.addLayout(row2)

    def update_info(self, info: ToolheadInfo):
        if info.active:
            label = info.display_name or info.name
            self._active_lbl.setText(label)
            self._active_lbl.setStyleSheet("font-size:11px; color:#ce93d8;")
        else:
            self._active_lbl.setText("None")
            self._active_lbl.setStyleSheet("font-size:11px; color:#555;")

    def _refresh(self):
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("…")
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        entries = self._client.fetch_toolhead_list()
        self._list_ready.emit(entries)

    def _populate(self, entries: list[tuple[str, str]]):
        self._combo.clear()
        self._names = []
        for name, display in entries:
            self._combo.addItem(display)
            self._names.append(name)
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↻")

    def _set(self):
        idx = self._combo.currentIndex()
        if 0 <= idx < len(self._names):
            self._client.set_toolhead(self._names[idx])

    def _clear(self):
        self._client.clear_toolhead()

    def update_client(self, client: SilaClient):
        self._client = client
        self._refresh()   # auto-populate on reconnect


class ToolheadManagerPanel(QWidget):
    """Dedicated tab for browsing installed toolheads and setting the active one.

    Left column: list of all toolheads on the server.
    Right column: details of the selected/active toolhead.

    The diagram widget is injected via the constructor so this panel never
    imports from another widget module.
    """

    _list_ready = Signal(list)   # emitted from bg thread → _populate on main thread

    def __init__(self, diagram, client: "SilaClient | None" = None):
        super().__init__()
        self._diagram = diagram   # ToolheadDiagramWidget instance, injected by MainWindow
        self._client: "SilaClient | None" = client
        self._names: list[str] = []
        self._active_info = ToolheadInfo()
        self._build()
        self._list_ready.connect(self._populate)

    def set_theme(self, t: dict):
        self._diagram.set_theme(t)

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setSpacing(12)
        outer.setContentsMargins(8, 8, 8, 8)

        # ── Left: active banner + list ─────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(6)

        active_box = QGroupBox("Active Toolhead")
        al = QVBoxLayout(active_box)
        self._active_lbl = QLabel("None")
        self._active_lbl.setStyleSheet("font-size:14px; font-weight:bold;")
        al.addWidget(self._active_lbl)
        self._clr_active_btn = QPushButton("Clear Active")
        self._clr_active_btn.setStyleSheet("color:#888;")
        self._clr_active_btn.clicked.connect(self._clear_active)
        self._clr_active_btn.setEnabled(False)
        al.addWidget(self._clr_active_btn)
        left.addWidget(active_box)

        list_box = QGroupBox("Installed Toolheads")
        ll = QVBoxLayout(list_box)
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_selection)
        ll.addWidget(self._list, 1)

        btns = QHBoxLayout()
        self._refresh_btn = QPushButton("↻ Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        btns.addWidget(self._refresh_btn)
        self._set_btn = QPushButton("Set as Active")
        self._set_btn.setStyleSheet("background:#1565c0; color:white;")
        self._set_btn.setEnabled(False)
        self._set_btn.clicked.connect(self._set_active)
        btns.addWidget(self._set_btn)
        ll.addLayout(btns)
        left.addWidget(list_box, 1)

        outer.addLayout(left, 1)

        # ── Right: diagram + details ────────────────────────────────────────
        right = QVBoxLayout()

        right.addWidget(self._diagram)

        detail_box = QGroupBox("Toolhead Details")
        dl = QVBoxLayout(detail_box)

        self._det_name = QLabel("Select a toolhead")
        self._det_name.setStyleSheet("font-size:14px; font-weight:bold; color:#ce93d8;")
        dl.addWidget(self._det_name)

        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setColumnStretch(1, 1)
        gl.setVerticalSpacing(4)
        self._det = {}
        for i, (key, label) in enumerate([
            ("footprint",     "Footprint"),
            ("offset",        "Body XY offset"),
            ("tip_xy",        "Tip XY offset"),
            ("tip_z",         "Tip depth Z"),
            ("z_engage",      "Engage depth"),
            ("manual_z",      "Requires manual Z"),
            ("manual_home",   "Requires manual home"),
        ]):
            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color:#666; font-size:11px;")
            val = QLabel("—")
            val.setStyleSheet("color:#aaa; font-size:11px; font-family:monospace;")
            gl.addWidget(lbl, i, 0)
            gl.addWidget(val, i, 1)
            self._det[key] = val
        dl.addWidget(grid)

        mount_row = QHBoxLayout()
        self._mount_btn = QPushButton("Confirm Toolhead Mounted")
        self._mount_btn.setStyleSheet("background:#22c55e; color:white; font-weight:bold;")
        self._mount_btn.clicked.connect(self._confirm_mounted)
        self._unmount_btn = QPushButton("Clear Mounted")
        self._unmount_btn.setStyleSheet("color:#888;")
        self._unmount_btn.clicked.connect(self._clear_mounted)
        mount_row.addWidget(self._mount_btn)
        mount_row.addWidget(self._unmount_btn)
        dl.addLayout(mount_row)
        dl.addStretch()

        right.addWidget(detail_box, 1)
        outer.addLayout(right, 1)

    # ── Public API ──────────────────────────────────────────────────────────

    def connect_client(self, client: "SilaClient"):
        """Wire up a live SiLA client; enable server-dependent actions and refresh."""
        self._client = client
        self._update_action_buttons()
        self._refresh()

    def disconnect_client(self):
        """Called when the SiLA connection drops; disable server-dependent actions."""
        self._client = None
        self._update_action_buttons()

    def _update_action_buttons(self):
        online = self._client is not None
        self._refresh_btn.setEnabled(online)
        self._set_btn.setEnabled(online and 0 <= self._list.currentRow() < len(self._names))
        self._mount_btn.setEnabled(online)
        self._unmount_btn.setEnabled(online)
        self._clr_active_btn.setEnabled(online)

    def update_info(self, info: ToolheadInfo):
        """Receives toolhead_updated signal."""
        self._active_info = info
        if info.active:
            label = info.display_name or info.name
            self._active_lbl.setText(label)
        else:
            self._active_lbl.setText("None")
        self._active_lbl.setToolTip("Mounted" if info.toolhead_mounted else "Not confirmed mounted")
        self._diagram.set_info(info if info.active else None)
        self._on_selection(self._list.currentRow())

    def update_client(self, client: "SilaClient"):
        self.connect_client(client)

    # ── Internals ───────────────────────────────────────────────────────────

    def _refresh(self):
        if not self._client:
            return
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("…")
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        entries = self._client.fetch_toolhead_list()
        self._list_ready.emit(entries)

    def _populate(self, entries: list[tuple[str, str]]):
        self._list.clear()
        self._names = []
        for name, display in entries:
            self._list.addItem(display)
            self._names.append(name)
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↻ Refresh")

    def _on_selection(self, row: int):
        self._set_btn.setEnabled(self._client is not None and 0 <= row < len(self._names))
        if 0 <= row < len(self._names):
            name = self._names[row]
            display = self._list.item(row).text()
            self._det_name.setText(display)
            info = self._active_info
            if info.active and name == info.name:
                self._det["footprint"].setText(
                    f"{info.footprint_x:.1f} × {info.footprint_y:.1f} mm"
                )
                self._det["offset"].setText(
                    f"X={info.offset_x:.1f},  Y={info.offset_y:.1f} mm"
                )
                self._det["tip_xy"].setText(
                    f"X={info.tip_x:.1f},  Y={info.tip_y:.1f} mm"
                )
                self._det["tip_z"].setText(f"{info.tip_offset_z:.1f} mm")
                self._det["z_engage"].setText(f"{info.z_engage:.1f} mm")
                self._det["manual_z"].setText("Yes" if info.requires_manual_z else "No")
                self._det["manual_home"].setText("Yes" if info.requires_manual_homing else "No")
                self._diagram.set_info(info)
            else:
                for f in self._det.values():
                    f.setText("— (set as active to view)")
                self._diagram.set_info(None)
        else:
            self._det_name.setText("Select a toolhead")
            for f in self._det.values():
                f.setText("—")
            self._diagram.set_info(None)

    def _set_active(self):
        if not self._client:
            return
        row = self._list.currentRow()
        if 0 <= row < len(self._names):
            self._client.set_toolhead(self._names[row])

    def _clear_active(self):
        if self._client:
            self._client.clear_toolhead()

    def _confirm_mounted(self):
        if self._client:
            self._client.confirm_toolhead_mounted()

    def _clear_mounted(self):
        if self._client:
            self._client.clear_toolhead_mounted()
