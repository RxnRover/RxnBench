from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QButtonGroup, QGridLayout,
)

from chem_bench_ui.sila_client import SilaClient


class JogPanel(QGroupBox):
    def __init__(self, client: SilaClient):
        super().__init__("Jog")
        self._client = client
        self._step = 5.0
        self._dev_mode = True
        self._build()

    def set_dev_mode(self, dev: bool):
        self._dev_mode = dev
        self.setVisible(dev)

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(6)

        # Step size
        row = QHBoxLayout()
        row.addWidget(QLabel("Step (mm):"))
        self._step_group = QButtonGroup(self)
        for label, val in [("0.1", 0.1), ("1", 1.0), ("5", 5.0), ("10", 10.0), ("50", 50.0)]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(40)
            btn.clicked.connect(lambda _, v=val: self._on_preset(v))
            self._step_group.addButton(btn)
            row.addWidget(btn)
            if val == 5.0:
                btn.setChecked(True)
        self._custom_step = QLineEdit()
        self._custom_step.setPlaceholderText("custom")
        self._custom_step.setFixedWidth(58)
        self._custom_step.setValidator(QDoubleValidator(0.01, 100.0, 2))
        self._custom_step.editingFinished.connect(self._apply_custom_step)
        row.addWidget(self._custom_step)
        row.addStretch()
        vbox.addLayout(row)

        # XY + Z buttons side by side
        controls = QHBoxLayout()

        xy = QGridLayout()
        xy.setSpacing(3)
        for label, dx, dy, r, c in [
            ("Y+", 0,  1, 0, 1),
            ("X-",-1,  0, 1, 0),
            ("X+", 1,  0, 1, 2),
            ("Y-", 0, -1, 2, 1),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(52, 52)
            btn.setStyleSheet("font-size:14px; font-weight:bold;")
            btn.clicked.connect(lambda _, x=dx, y=dy: self._jog_xy(x, y))
            xy.addWidget(btn, r, c)
        center = QLabel("⊕")
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setStyleSheet("color:#444; font-size:20px;")
        xy.addWidget(center, 1, 1)
        controls.addLayout(xy)

        controls.addSpacing(12)

        z_col = QVBoxLayout()
        z_col.setSpacing(3)
        z_up = QPushButton("Z+")
        z_dn = QPushButton("Z-")
        for btn in (z_up, z_dn):
            btn.setFixedSize(52, 52)
            btn.setStyleSheet("font-size:14px; font-weight:bold; background:#2d1f50;")
        z_up.clicked.connect(lambda: self._jog_z(1))
        z_dn.clicked.connect(lambda: self._jog_z(-1))
        z_lbl = QLabel("Z")
        z_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        z_lbl.setStyleSheet("color:#666;")
        z_col.addWidget(z_up)
        z_col.addWidget(z_lbl)
        z_col.addWidget(z_dn)
        controls.addLayout(z_col)
        controls.addStretch()
        vbox.addLayout(controls)

        hint = QLabel("Click grid to move  |  Arrow keys = XY  |  PgUp / PgDn = Z")
        hint.setStyleSheet("color:#444; font-size:9px;")
        vbox.addWidget(hint)

    def _on_preset(self, val: float):
        self._step = val
        self._custom_step.clear()

    def _apply_custom_step(self):
        text = self._custom_step.text().strip()
        if not text:
            return
        try:
            val = float(text)
        except ValueError:
            self._custom_step.clear()
            return
        val = max(0.01, min(100.0, val))
        self._custom_step.setText(f"{val:g}")
        self._step = val
        for btn in self._step_group.buttons():
            btn.setChecked(False)

    def _jog_xy(self, dx, dy):
        self._client.jog(dx=dx * self._step, dy=dy * self._step)

    def _jog_z(self, dz):
        self._client.jog(dz=dz * self._step)

    def handle_key(self, key):
        mapping = {
            Qt.Key.Key_Left:     (-1, 0, 0),
            Qt.Key.Key_Right:    ( 1, 0, 0),
            Qt.Key.Key_Up:       ( 0, 1, 0),
            Qt.Key.Key_Down:     ( 0,-1, 0),
            Qt.Key.Key_PageUp:   ( 0, 0, 1),
            Qt.Key.Key_PageDown: ( 0, 0,-1),
        }
        if key in mapping:
            dx, dy, dz = mapping[key]
            self._client.jog(
                dx=dx * self._step,
                dy=dy * self._step,
                dz=dz * self._step,
            )

    def update_client(self, c: SilaClient):
        self._client = c
