"""
Camera widget - minimal MDI sub-window: live image view + capture interval control.

No .ui file here on purpose - this is meant to be copy-pasted and grown, not
loaded from a designer file. See devices/ph_sensor/frontend/widget.py for a
fuller example (custom-painted history graph, .ui-loaded layout) once this
needs to grow beyond a single image view.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...discovery import DiscoveredServer
from .connection import CameraConnection


class CameraWidget(QWidget):
    """MDI sub-window for Camera: live image view and a capture-interval control."""

    preferred_mdi_size = (360, 320)

    def __init__(self, server: DiscoveredServer, t: dict,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server = server
        self._t = t

        self._status_lbl = QLabel("Connecting…")

        self._image_lbl = QLabel("No image yet")
        self._image_lbl.setMinimumSize(320, 240)
        self._image_lbl.setScaledContents(False)

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.1, 3600.0)
        self._interval_spin.setValue(30.0)
        self._interval_spin.setSuffix(" s")
        self._interval_btn = QPushButton("Set Capture Interval")

        interval_row = QHBoxLayout()
        interval_row.addWidget(self._interval_spin)
        interval_row.addWidget(self._interval_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_lbl)
        layout.addWidget(self._image_lbl)
        layout.addLayout(interval_row)

        self._apply_theme()
        self._interval_btn.clicked.connect(self._on_set_interval)

        self._client = CameraConnection()
        self._client.latest_image_updated.connect(self._on_image)
        self._client.connection_changed.connect(self._on_connection)
        self._client.error_occurred.connect(self._on_error)
        self._client.connect_to(server.host, server.port)

    def _apply_theme(self) -> None:
        t = self._t
        self.setStyleSheet(f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}")

    def _on_connection(self, ready: bool) -> None:
        self._status_lbl.setText("Connected" if ready else "Connecting…")

    def _on_image(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self._image_lbl.setPixmap(
                pixmap.scaled(self._image_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio)
            )
        else:
            self._image_lbl.setText("Received unreadable image data")

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg[:60]}")

    def _on_set_interval(self) -> None:
        self._client.set_capture_interval(self._interval_spin.value())

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and repaint."""
        self._t = t
        self._apply_theme()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Disconnect the gRPC client when the sub-window is closed."""
        self._client.close()
        super().closeEvent(event)
