"""
MyDevice widget - minimal MDI sub-window: live measurement + one action control.

No .ui file here on purpose - this is meant to be copy-pasted and grown, not
loaded from a designer file. See devices/ph_sensor/capability/frontend/widget.py for a
fuller example (custom-painted history graph, .ui-loaded layout) once you
outgrow this.

TODO: rename MyDeviceWidget and replace the measurement/action labels with
      your device's real fields.
"""
from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from rxn_bench_ui.discovery import DiscoveredServer
from .connection import MyDeviceConnection


class MyDeviceWidget(QWidget):
    """MDI sub-window for MyDevice: live measurement display and one action button."""

    preferred_mdi_size = (280, 160)

    def __init__(self, server: DiscoveredServer, t: dict,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server = server
        self._t = t
        self._last_value = float("nan")

        self._status_lbl = QLabel("Connecting…")
        self._value_lbl = QLabel("-")
        self._param_spin = QDoubleSpinBox()
        self._param_spin.setRange(-1000.0, 1000.0)
        self._action_btn = QPushButton("Perform Action")

        param_row = QHBoxLayout()
        param_row.addWidget(self._param_spin)
        param_row.addWidget(self._action_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_lbl)
        layout.addWidget(self._value_lbl)
        layout.addLayout(param_row)

        self._apply_theme()
        self._action_btn.clicked.connect(self._on_action)

        self._client = MyDeviceConnection()
        self._client.measurement_updated.connect(self._on_measurement)
        self._client.connection_changed.connect(self._on_connection)
        self._client.error_occurred.connect(self._on_error)
        self._client.connect_to(server.host, server.port)

    def _apply_theme(self) -> None:
        t = self._t
        self.setStyleSheet(f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}")

    def _on_connection(self, ready: bool) -> None:
        self._status_lbl.setText("Connected" if ready else "Connecting…")

    def _on_measurement(self, value: float) -> None:
        self._last_value = value
        self._value_lbl.setText(f"{value:.2f}" if not math.isnan(value) else "-")

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg[:60]}")

    def _on_action(self) -> None:
        self._client.perform_action(self._param_spin.value())

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and repaint."""
        self._t = t
        self._apply_theme()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Disconnect the gRPC client when the sub-window is closed."""
        self._client.close()
        super().closeEvent(event)
