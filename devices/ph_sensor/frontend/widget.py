"""pH Sensor widget - live pH reading, history graph, and calibration controls."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QFile, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from ...discovery import DiscoveredServer
from .connection import PHConnection

_UI_DIR = Path(__file__).parent / "ui"

# (point key, default pH for spin box)
_CAL_POINTS = [
    ("mid",   7.00),
    ("low",   4.00),
    ("high", 10.00),
    ("clear", 7.00),
]


def _ph_color(ph: float) -> str:
    """Smooth red to green to blue hex color across pH 0-14."""
    if math.isnan(ph):
        return "#64748b"
    ph = max(0.0, min(14.0, ph))
    if ph <= 7.0:
        t = ph / 7.0
        r = int(239 + t * (34  - 239))
        g = int(68  + t * (197 - 68))
        b = int(68  + t * (94  - 68))
    else:
        t = (ph - 7.0) / 7.0
        r = int(34  + t * (59  - 34))
        g = int(197 + t * (130 - 197))
        b = int(94  + t * (246 - 94))
    return f"#{r:02x}{g:02x}{b:02x}"


# Mini line-graph widget

class PHGraph(QWidget):
    """
    Scrolling pH history chart. Stores up to _MAX readings at 1 Hz -> 2 min
    of history. Y axis fixed at 0-14; reference lines at pH 4, 7, 10.
    Each line segment is coloured by the pH value at that point.
    """
    _MAX  = 120
    _REFS = [4.0, 7.0, 10.0]

    def __init__(self, t: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t        = t
        self._readings: list[float] = []
        self.setMinimumHeight(80)

    def add_reading(self, ph: float) -> None:
        self._readings.append(ph)
        if len(self._readings) > self._MAX:
            self._readings.pop(0)
        self.update()

    def set_theme(self, t: dict) -> None:
        self._t = t
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        t = self._t

        w, h   = self.width(), self.height()
        pad_l  = 24   # space for axis labels
        pad_r  = 4
        pad_t  = 4
        pad_b  = 4
        gw     = w - pad_l - pad_r
        gh     = h - pad_t - pad_b

        # Background + border
        painter.fillRect(0, 0, w, h, QColor(t["widget_bg"]))
        painter.setPen(QPen(QColor(t["border"]), 1))
        painter.drawRect(pad_l, pad_t, gw, gh)

        def ph_y(ph: float) -> int:
            return int(pad_t + gh - (ph / 14.0) * gh)

        # Reference lines & labels
        small_font = painter.font()
        small_font.setPointSize(7)
        painter.setFont(small_font)
        for ref in self._REFS:
            y = ph_y(ref)
            pen = QPen(QColor(t["border"]), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(pad_l + 1, y, pad_l + gw - 1, y)
            painter.setPen(QColor(t["text_dim"]))
            painter.drawText(1, y + 4, str(int(ref)))

        # Line plot (right-aligned: newest reading on the right)
        readings = self._readings
        n = len(readings)
        if n < 2:
            return

        max_n = self._MAX
        for i in range(n - 1):
            ph_mid = (readings[i] + readings[i + 1]) / 2.0
            pen = QPen(QColor(_ph_color(ph_mid)), 2.0, Qt.SolidLine,
                       Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            # right-align: slot (max_n - n + i) out of (max_n - 1) total slots
            slot0 = max_n - n + i
            slot1 = slot0 + 1
            x1 = int(pad_l + (slot0 / (max_n - 1)) * gw)
            x2 = int(pad_l + (slot1 / (max_n - 1)) * gw)
            y1 = ph_y(readings[i])
            y2 = ph_y(readings[i + 1])
            painter.drawLine(x1, y1, x2, y2)


# Main widget

class PHSensorWidget(QWidget):
    """MDI sub-window for the pH sensor: live pH display and calibration controls."""

    preferred_mdi_size = (320, 420)

    def __init__(self, server: DiscoveredServer, t: dict,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server  = server
        self._t       = t
        self._last_ph = float("nan")

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "ph_sensor_widget.ui"))
        f.open(QFile.ReadOnly)
        self._ui = loader.load(f, self)
        f.close()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._ui)

        self._connected = False
        self._find_children()
        self._inject_graph()
        self._apply_theme()
        self._wire()

        self._server_addr_lbl.setText(f"{server.host}:{server.port}")

        self._client = PHConnection()
        self._client.ph_updated.connect(self._on_ph)
        self._client.slope_ready.connect(self._on_slope)
        self._client.connection_changed.connect(self._on_connection)
        self._client.error_occurred.connect(self._on_error)
        self._client.connect_to(server.host, server.port)


    def _find_children(self) -> None:
        ui = self._ui
        self._conn_dot_lbl:    QLabel         = ui.findChild(QLabel,         "conn_dot_lbl")
        self._conn_status_lbl: QLabel         = ui.findChild(QLabel,         "conn_status_lbl")
        self._server_addr_lbl: QLabel         = ui.findChild(QLabel,         "server_addr_lbl")
        self._ph_value_lbl:    QLabel         = ui.findChild(QLabel,         "ph_value_lbl")
        self._ph_unit_lbl:     QLabel         = ui.findChild(QLabel,         "ph_unit_lbl")
        self._graph_placeholder: QWidget      = ui.findChild(QWidget,        "ph_graph_placeholder")
        self._slope_lbl:       QLabel         = ui.findChild(QLabel,         "slope_lbl")
        self._read_slope_btn:  QPushButton    = ui.findChild(QPushButton,    "read_slope_btn")
        self._cal_point_combo: QComboBox      = ui.findChild(QComboBox,      "cal_point_combo")
        self._cal_value_lbl:   QLabel         = ui.findChild(QLabel,         "cal_value_lbl")
        self._cal_value_spin:  QDoubleSpinBox = ui.findChild(QDoubleSpinBox, "cal_value_spin")
        self._cal_run_btn:     QPushButton    = ui.findChild(QPushButton,    "cal_run_btn")

    def _inject_graph(self) -> None:
        """Replace the QWidget placeholder with a PHGraph."""
        self._graph = PHGraph(self._t, self._graph_placeholder)
        lay = QVBoxLayout(self._graph_placeholder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._graph)


    def _apply_theme(self) -> None:
        t      = self._t
        text   = t["text"]
        muted  = t["text_muted"]
        border = t["border"]
        raised = t["bg_raised"]

        self._ui.setStyleSheet(
            f"QWidget {{ background: {t['widget_bg']}; color: {text}; }}"
            f"QGroupBox {{"
            f"  border: 1px solid {border}; border-radius: 4px;"
            f"  margin-top: 8px; padding-top: 4px; }}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin; left: 8px;"
            f"  color: {muted}; font-weight: bold; }}"
        )

        for lbl in (self._conn_dot_lbl, self._conn_status_lbl,
                    self._server_addr_lbl, self._ph_unit_lbl):
            if lbl:
                lbl.setStyleSheet(f"color: {muted}; font-size: 9pt;")

        if self._slope_lbl:
            self._slope_lbl.setStyleSheet(f"color: {muted}; font-size: 9pt;")
        if self._cal_value_lbl:
            self._cal_value_lbl.setStyleSheet(f"color: {text};")

        # Small icon buttons (refresh)
        icon_btn_ss = (
            f"QPushButton {{ background: {raised}; color: {text};"
            f"  border: 1px solid {border}; border-radius: 3px; padding: 2px 4px; }}"
            f"QPushButton:hover {{ border-color: {t['accent']}; }}"
        )
        if self._read_slope_btn:
            self._read_slope_btn.setStyleSheet(icon_btn_ss)

        if self._cal_run_btn:
            self._cal_run_btn.setStyleSheet(icon_btn_ss)

        input_ss = (
            f"background: {t['bg_surface']}; color: {text}; border: 1px solid {border};"
            f" border-radius: 3px; padding: 2px 6px;"
        )
        if self._cal_value_spin:  self._cal_value_spin.setStyleSheet(input_ss)
        if self._cal_point_combo: self._cal_point_combo.setStyleSheet(input_ss)

        self._update_ph_display()
        if self._graph:
            self._graph.set_theme(t)

    def _update_ph_display(self) -> None:
        ph    = self._last_ph
        color = _ph_color(ph)
        t     = self._t
        text  = f"{ph:.2f}" if not math.isnan(ph) else "-"

        if self._ph_value_lbl:
            self._ph_value_lbl.setText(text)
            self._ph_value_lbl.setStyleSheet(
                f"color: {color};"
                f" background: {t['bg_surface']};"
                f" border: 2px solid {color};"
                f" border-radius: 8px; padding: 8px;"
            )


    def _wire(self) -> None:
        if self._read_slope_btn:
            self._read_slope_btn.clicked.connect(self._on_read_slope)
        if self._cal_point_combo:
            self._cal_point_combo.currentIndexChanged.connect(self._on_point_changed)
        if self._cal_run_btn:
            self._cal_run_btn.clicked.connect(self._on_calibrate)
        self._on_point_changed(0)


    def _on_connection(self, ready: bool) -> None:
        self._connected = ready
        t = self._t
        if self._conn_dot_lbl:
            self._conn_dot_lbl.setStyleSheet(
                f"color: {t['dot_ok'] if ready else t['dot_err']};"
            )
        if self._conn_status_lbl:
            self._conn_status_lbl.setText("Connected" if ready else "Connecting…")
            self._conn_status_lbl.setStyleSheet(
                f"color: {t['text'] if ready else t['text_muted']}; font-size: 9pt;"
            )

    def _on_ph(self, ph: float) -> None:
        self._last_ph = ph
        self._update_ph_display()
        self._graph.add_reading(ph)

    def _on_slope(self, text: str) -> None:
        if self._slope_lbl:
            self._slope_lbl.setText(f"Slope: {text}" if text else "Slope: -")

    def _on_error(self, msg: str) -> None:
        if self._conn_status_lbl:
            self._conn_status_lbl.setText(f"Error: {msg[:60]}")
            self._conn_status_lbl.setStyleSheet(
                f"color: {self._t['error']}; font-size: 9pt;"
            )

    def _on_read_slope(self) -> None:
        if self._slope_lbl:
            self._slope_lbl.setText("Slope: reading…")
        self._client.fetch_slope()

    def _on_point_changed(self, index: int) -> None:
        if index < 0 or index >= len(_CAL_POINTS):
            return
        point, default_ph = _CAL_POINTS[index]
        is_clear = point == "clear"
        if self._cal_value_spin:
            self._cal_value_spin.setValue(default_ph)
            self._cal_value_spin.setEnabled(not is_clear)
        if self._cal_value_lbl:
            self._cal_value_lbl.setEnabled(not is_clear)

    def _on_calibrate(self) -> None:
        idx = self._cal_point_combo.currentIndex() if self._cal_point_combo else 0
        if idx < 0 or idx >= len(_CAL_POINTS):
            return
        point, _ = _CAL_POINTS[idx]
        value     = self._cal_value_spin.value() if self._cal_value_spin else 7.0

        if self._cal_run_btn:
            self._cal_run_btn.setEnabled(False)

        self._client.calibrate(point, value)

        QTimer.singleShot(3000, lambda: (
            self._cal_run_btn.setEnabled(True) if self._cal_run_btn else None
        ))


    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and repaint all widget elements."""
        self._t = t
        self._apply_theme()
        self._on_connection(self._connected)


    def closeEvent(self, event) -> None:  # noqa: N802
        """Disconnect the gRPC client when the sub-window is closed."""
        self._client.close()
        super().closeEvent(event)
