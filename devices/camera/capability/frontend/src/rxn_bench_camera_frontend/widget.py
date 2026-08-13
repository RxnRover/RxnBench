"""
Camera widget - minimal MDI sub-window: just the live image view.

No capture-interval control - the widget sets a fixed cadence once connected
(see _DEFAULT_CAPTURE_INTERVAL_S) instead of exposing it as an operator-facing
knob. SetCaptureInterval is still a real SiLA command (scripts/other clients
can still call it); it's just not surfaced in this widget.

No .ui file here on purpose - this is meant to be copy-pasted and grown, not
loaded from a designer file. See devices/ph_sensor/capability/frontend/widget.py for a
fuller example (custom-painted history graph, .ui-loaded layout) once this
needs to grow beyond a single image view.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from rxn_bench_ui.discovery import DiscoveredServer
from .connection import CameraConnection

_DEFAULT_CAPTURE_INTERVAL_S = 5.0


class CameraWidget(QWidget):
    """MDI sub-window for Camera: just the live image view."""

    preferred_mdi_size = (360, 320)

    def __init__(self, server: DiscoveredServer, t: dict,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server = server
        self._t = t
        self._raw_pixmap: QPixmap | None = None  # unscaled; re-scaled on resize

        self._status_lbl = QLabel("Connecting…")

        self._image_lbl = QLabel("No image yet")
        self._image_lbl.setObjectName("cameraImageLabel")
        self._image_lbl.setMinimumSize(320, 240)
        self._image_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_lbl.setScaledContents(False)
        # Own background instead of relying on the parent's cascaded style,
        # so the letterboxed area around a smaller-than-label pixmap always
        # repaints cleanly.
        self._image_lbl.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_lbl)
        layout.addWidget(self._image_lbl, 1)

        self._apply_theme()

        self._client = CameraConnection()
        self._client.latest_image_updated.connect(self._on_image)
        self._client.connection_changed.connect(self._on_connection)
        self._client.error_occurred.connect(self._on_error)
        self._client.connect_to(server.host, server.port)

    def _apply_theme(self) -> None:
        t = self._t
        self.setStyleSheet(
            f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}"
            f"QLabel#cameraImageLabel {{ background: {t['widget_bg']}; }}"
        )

    def _on_connection(self, ready: bool) -> None:
        self._status_lbl.setText("Connected" if ready else "Connecting…")
        if ready:
            # No UI control for this - just start the camera at a sane fixed
            # cadence instead of leaving it at whatever the server's own
            # default happens to be.
            self._client.set_capture_interval(_DEFAULT_CAPTURE_INTERVAL_S)

    def _on_image(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self._raw_pixmap = pixmap
            self._render_pixmap()
        else:
            self._raw_pixmap = None
            self._image_lbl.setText("Received unreadable image data")

    def _render_pixmap(self) -> None:
        """(Re-)scale the last received frame to the label's current size.

        Split out from _on_image so resizing the sub-window rescales the
        already-received frame too, instead of leaving a stale-sized pixmap.
        """
        if self._raw_pixmap is None:
            return
        self._image_lbl.setPixmap(
            self._raw_pixmap.scaled(
                self._image_lbl.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render_pixmap()

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg[:60]}")

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and repaint."""
        self._t = t
        self._apply_theme()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Disconnect the gRPC client when the sub-window is closed."""
        self._client.close()
        super().closeEvent(event)
