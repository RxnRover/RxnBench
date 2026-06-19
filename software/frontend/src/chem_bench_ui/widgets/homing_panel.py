from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from chem_bench_ui.sila_client import SilaClient


class HomingPanel(QGroupBox):
    """Per-axis homing panel. Each axis can be homed independently in any order."""

    def __init__(self, client: SilaClient):
        super().__init__("Homing")
        self._client = client
        self._manual_active = False
        self._done = {k: False for k in ("x_min", "x_max", "y_min", "y_max", "z")}
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(4)

        # Status
        self._status_lbl = QLabel()
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("font-size:10px;")
        vbox.addWidget(self._status_lbl)

        # Top action row
        top = QHBoxLayout()
        self._auto_btn = QPushButton("Auto Home XY")
        self._auto_btn.setStyleSheet("background:#1565c0; color:white; font-size:11px;")
        self._auto_btn.clicked.connect(self._auto_home)
        top.addWidget(self._auto_btn)
        self._manual_btn = QPushButton("Start Manual")
        self._manual_btn.setStyleSheet("background:#e65100; color:white; font-size:11px;")
        self._manual_btn.clicked.connect(self._start_manual)
        top.addWidget(self._manual_btn)
        vbox.addLayout(top)

        # Divider
        div = QLabel()
        div.setFixedHeight(1)
        div.setStyleSheet("background:#2a2d3e; margin-top:2px;")
        vbox.addWidget(div)

        # X axis
        vbox.addWidget(self._axis_label("X axis — jog to each physical limit"))
        row_x = QHBoxLayout()
        self._x_min_btn = self._confirm_btn("X−")
        self._x_max_btn = self._confirm_btn("X+")
        self._x_min_btn.clicked.connect(self._confirm_x_min)
        self._x_max_btn.clicked.connect(self._confirm_x_max)
        row_x.addWidget(self._x_min_btn)
        row_x.addWidget(self._x_max_btn)
        vbox.addLayout(row_x)

        # Y axis
        vbox.addWidget(self._axis_label("Y axis — jog to each physical limit"))
        row_y = QHBoxLayout()
        self._y_min_btn = self._confirm_btn("Y−")
        self._y_max_btn = self._confirm_btn("Y+")
        self._y_min_btn.clicked.connect(self._confirm_y_min)
        self._y_max_btn.clicked.connect(self._confirm_y_max)
        row_y.addWidget(self._y_min_btn)
        row_y.addWidget(self._y_max_btn)
        vbox.addLayout(row_y)

        # Z axis
        vbox.addWidget(self._axis_label("Z axis — jog tip to reference surface"))
        row_z = QHBoxLayout()
        self._z_btn = QPushButton("Set Z Reference")
        self._z_btn.setStyleSheet("background:#2e7d32; color:white; font-size:11px;")
        self._z_btn.clicked.connect(self._confirm_z)
        row_z.addWidget(self._z_btn)
        row_z.addStretch()
        vbox.addLayout(row_z)

        # Reset
        reset = QPushButton("Reset All")
        reset.setStyleSheet("color:#555; font-size:10px; margin-top:2px;")
        reset.clicked.connect(self._reset)
        vbox.addWidget(reset)

        self._refresh()

    def _axis_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#555; font-size:9px; margin-top:3px;")
        return lbl

    def _confirm_btn(self, label: str) -> QPushButton:
        btn = QPushButton(f"Confirm {label}")
        btn.setStyleSheet("font-size:11px;")
        btn.setEnabled(False)
        return btn

    def _refresh(self):
        d = self._done
        x_ok = d["x_min"] and d["x_max"]
        y_ok = d["y_min"] and d["y_max"]
        z_ok = d["z"]
        active = self._manual_active

        def _style_xy(btn, done):
            if done:
                btn.setEnabled(False)
                btn.setStyleSheet("font-size:11px; background:#1b5e20; color:#666;")
            elif active:
                btn.setEnabled(True)
                btn.setStyleSheet("font-size:11px;")
            else:
                btn.setEnabled(False)
                btn.setStyleSheet("font-size:11px; color:#444;")

        _style_xy(self._x_min_btn, d["x_min"])
        _style_xy(self._x_max_btn, d["x_max"])
        _style_xy(self._y_min_btn, d["y_min"])
        _style_xy(self._y_max_btn, d["y_max"])

        # Z is always available (re-reference any time)
        if z_ok:
            self._z_btn.setText("✓ Z Referenced")
            self._z_btn.setStyleSheet("background:#1b5e20; color:#aaa; font-size:11px;")
        else:
            self._z_btn.setText("Set Z Reference")
            self._z_btn.setStyleSheet("background:#2e7d32; color:white; font-size:11px;")
        self._z_btn.setEnabled(True)

        # Status line
        missing = (["X"] if not x_ok else []) + (["Y"] if not y_ok else []) + (["Z"] if not z_ok else [])
        if not missing:
            self._status_lbl.setText("✓ All axes homed")
            self._status_lbl.setStyleSheet("font-size:10px; color:#00e676;")
        elif active:
            self._status_lbl.setText(f"Manual homing active — still needed: {', '.join(missing)}")
            self._status_lbl.setStyleSheet("font-size:10px; color:#ff9800;")
        else:
            self._status_lbl.setText(f"Not homed: {', '.join(missing)}")
            self._status_lbl.setStyleSheet("font-size:10px; color:#888;")

    def _auto_home(self):
        self._client.home_auto()
        for k in ("x_min", "x_max", "y_min", "y_max"):
            self._done[k] = True
        self._refresh()

    def _start_manual(self):
        self._client.start_manual_homing()
        self._manual_active = True
        self._refresh()

    def _confirm_x_min(self):
        self._client.confirm_x_min()
        self._done["x_min"] = True
        self._refresh()
        self._check_finish()

    def _confirm_x_max(self):
        self._client.confirm_x_max()
        self._done["x_max"] = True
        self._refresh()
        self._check_finish()

    def _confirm_y_min(self):
        self._client.confirm_y_min()
        self._done["y_min"] = True
        self._refresh()
        self._check_finish()

    def _confirm_y_max(self):
        self._client.confirm_y_max()
        self._done["y_max"] = True
        self._refresh()
        self._check_finish()

    def _confirm_z(self):
        self._client.confirm_z_reference()
        self._done["z"] = True
        self._refresh()
        self._check_finish()

    def _check_finish(self):
        if all(self._done.values()) and self._manual_active:
            self._client.finish_homing()
            self._manual_active = False
            self._refresh()

    def _reset(self):
        self._done = {k: False for k in self._done}
        self._manual_active = False
        self._refresh()

    def update_client(self, client: SilaClient):
        self._client = client
