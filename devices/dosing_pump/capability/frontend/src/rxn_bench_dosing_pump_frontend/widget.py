"""Dosing pump widget - live dispensed volume, history graph, and dosing controls."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QFile, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from rxn_bench_ui.discovery import DiscoveredServer
from .connection import DosingPumpConnection

_UI_DIR = Path(__file__).parent / "ui"

# This widget serves the DosingPump SiLA feature, not one vendor's pump: any
# server advertising that feature is matched to it by FEATURE_FRAGMENTS. So no
# model-specific numbers belong here - the Rate ceiling is taken from the
# server's MaxFlowRate at runtime, and out-of-range requests are rejected by
# the device itself and surfaced through error_occurred.
#
# Dispensing modes: (label, which inputs apply, what the mode actually does).
# The action button keeps one stable verb across all four - the mode combo
# already says which kind of dispense it is, and a per-mode verb ("Hold Rate")
# reads as though it might freeze the pump rather than start it.
_VOLUME, _MINUTES, _RATE = "volume", "minutes", "rate"
_MODES = [
    ("Volume", {_VOLUME},
     "Dispense a fixed volume, then stop."),
    ("Dose over time", {_VOLUME, _MINUTES},
     "Spread a fixed volume evenly over the time set."),
    ("Constant rate", {_RATE, _MINUTES},
     "Hold a metered flow rate for the time set, or until stopped.\n"
     "Capped at the metered maximum the pump reports, which is below\n"
     "its top speed and depends on calibration."),
    ("Continuous", set(),
     "Run at the pump's top speed until stopped.\n"
     "Rate is not adjustable in this mode - use Constant rate for that."),
]


# Mini line-graph widget

class VolumeGraph(QWidget):
    """
    Scrolling dispensed-volume history. Stores up to _MAX readings at 1 Hz -> 2 min
    of history. Y axis auto-scales to the largest volume seen, since a dose can be
    0.5 ml or 500 ml; the axis label reports the current top.
    """
    _MAX = 120

    def __init__(self, t: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = t
        self._readings: list[float] = []
        self._active = False
        self.setMinimumHeight(80)

    def add_reading(self, volume: float) -> None:
        self._readings.append(volume)
        if len(self._readings) > self._MAX:
            self._readings.pop(0)
        self.update()

    def set_active(self, active: bool) -> None:
        """Colour the trace by whether the pump is currently running."""
        if active != self._active:
            self._active = active
            self.update()

    def set_theme(self, t: dict) -> None:
        self._t = t
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        t = self._t

        w, h = self.width(), self.height()
        pad_l = 34   # space for axis labels (volumes are wider than pH values)
        pad_r = 4
        pad_t = 4
        pad_b = 4
        gw = w - pad_l - pad_r
        gh = h - pad_t - pad_b

        # Background + border
        painter.fillRect(0, 0, w, h, QColor(t["widget_bg"]))
        painter.setPen(QPen(QColor(t["border"]), 1))
        painter.drawRect(pad_l, pad_t, gw, gh)

        readings = self._readings
        # Round the top up to something readable rather than the raw maximum.
        peak = max([abs(v) for v in readings] + [1.0])
        top = _axis_top(peak)

        def vol_y(volume: float) -> int:
            return int(pad_t + gh - (min(abs(volume), top) / top) * gh)

        # Reference lines & labels at 0, half, full
        small_font = painter.font()
        small_font.setPointSize(7)
        painter.setFont(small_font)
        for ref in (0.0, top / 2.0, top):
            y = vol_y(ref)
            painter.setPen(QPen(QColor(t["border"]), 1, Qt.DashLine))
            painter.drawLine(pad_l + 1, y, pad_l + gw - 1, y)
            painter.setPen(QColor(t["text_dim"]))
            painter.drawText(1, y + 4, f"{ref:g}")

        n = len(readings)
        if n < 2:
            return

        # Line plot (right-aligned: newest reading on the right)
        colour = QColor(t["accent"] if self._active else t["text_muted"])
        painter.setPen(QPen(colour, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        max_n = self._MAX
        for i in range(n - 1):
            slot0 = max_n - n + i
            x1 = int(pad_l + (slot0 / (max_n - 1)) * gw)
            x2 = int(pad_l + ((slot0 + 1) / (max_n - 1)) * gw)
            painter.drawLine(x1, vol_y(readings[i]), x2, vol_y(readings[i + 1]))


def _axis_top(peak: float) -> float:
    """Round *peak* up to a 1/2/5 x 10^n step so the axis labels stay readable."""
    exponent = math.floor(math.log10(peak))
    base = 10.0 ** exponent
    for step in (1.0, 2.0, 5.0, 10.0):
        if peak <= step * base:
            return step * base
    return 10.0 * base


# Main widget

class DosingPumpWidget(QWidget):
    """MDI sub-window for the dosing pump: live dispense progress and dosing controls."""

    preferred_mdi_size = (340, 650)

    def __init__(self, server: DiscoveredServer, t: dict,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server = server
        self._t = t
        self._volume = float("nan")
        self._running = False
        self._paused = False
        self._connected = False

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "dosing_pump_widget.ui"))
        f.open(QFile.ReadOnly)
        self._ui = loader.load(f, self)
        f.close()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._ui)

        self._find_children()
        self._inject_graph()
        self._apply_theme()

        # Built before _wire(): the button hookups bind client methods directly.
        self._client = DosingPumpConnection()
        self._wire()
        self._client.volume_dispensed_updated.connect(self._on_volume)
        self._client.dispensing_updated.connect(self._on_dispensing)
        self._client.stopped.connect(self._on_stopped)
        self._client.totals_ready.connect(self._on_totals)
        self._client.limits_ready.connect(self._on_limits)
        self._client.connection_changed.connect(self._on_connection)
        self._client.error_occurred.connect(self._on_error)

        self._server_addr_lbl.setText(f"{server.host}:{server.port}")
        self._client.connect_to(server.host, server.port)

    def _find_children(self) -> None:
        ui = self._ui
        self._conn_dot_lbl:      QLabel         = ui.findChild(QLabel,         "conn_dot_lbl")
        self._conn_status_lbl:   QLabel         = ui.findChild(QLabel,         "conn_status_lbl")
        self._server_addr_lbl:   QLabel         = ui.findChild(QLabel,         "server_addr_lbl")
        self._volume_value_lbl:  QLabel         = ui.findChild(QLabel,         "volume_value_lbl")
        self._volume_unit_lbl:   QLabel         = ui.findChild(QLabel,         "volume_unit_lbl")
        self._state_lbl:         QLabel         = ui.findChild(QLabel,         "state_lbl")
        self._graph_placeholder: QWidget        = ui.findChild(QWidget,        "volume_graph_placeholder")
        self._pause_btn:         QPushButton    = ui.findChild(QPushButton,    "pause_btn")
        self._stop_btn:          QPushButton    = ui.findChild(QPushButton,    "stop_btn")
        self._mode_combo:        QComboBox      = ui.findChild(QComboBox,      "mode_combo")
        self._volume_lbl:        QLabel         = ui.findChild(QLabel,         "volume_lbl")
        self._volume_spin:       QDoubleSpinBox = ui.findChild(QDoubleSpinBox, "volume_spin")
        self._rate_lbl:          QLabel         = ui.findChild(QLabel,         "rate_lbl")
        self._rate_spin:         QDoubleSpinBox = ui.findChild(QDoubleSpinBox, "rate_spin")
        self._minutes_lbl:       QLabel         = ui.findChild(QLabel,         "minutes_lbl")
        self._minutes_spin:      QDoubleSpinBox = ui.findChild(QDoubleSpinBox, "minutes_spin")
        self._reverse_check:     QCheckBox      = ui.findChild(QCheckBox,      "reverse_check")
        self._run_btn:           QPushButton    = ui.findChild(QPushButton,    "run_btn")
        self._totals_lbl:        QLabel         = ui.findChild(QLabel,         "totals_lbl")
        self._limits_lbl:        QLabel         = ui.findChild(QLabel,         "limits_lbl")
        self._clear_totals_btn:  QPushButton    = ui.findChild(QPushButton,    "clear_totals_btn")
        self._refresh_btn:       QPushButton    = ui.findChild(QPushButton,    "refresh_btn")
        self._cal_lbl:           QLabel         = ui.findChild(QLabel,         "cal_lbl")
        self._cal_spin:          QDoubleSpinBox = ui.findChild(QDoubleSpinBox, "cal_spin")
        self._cal_run_btn:       QPushButton    = ui.findChild(QPushButton,    "cal_run_btn")

    def _inject_graph(self) -> None:
        """Replace the QWidget placeholder with a VolumeGraph."""
        self._graph = VolumeGraph(self._t, self._graph_placeholder)
        lay = QVBoxLayout(self._graph_placeholder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._graph)


    def _apply_theme(self) -> None:
        t = self._t
        text = t["text"]
        muted = t["text_muted"]
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

        for lbl in (self._conn_dot_lbl, self._conn_status_lbl, self._server_addr_lbl,
                    self._volume_unit_lbl, self._totals_lbl, self._limits_lbl):
            if lbl:
                lbl.setStyleSheet(f"color: {muted}; font-size: 9pt;")

        # Setting any stylesheet replaces Qt's default disabled palette, so the
        # :disabled state has to be spelled out or mode-gated inputs still look
        # active.
        for lbl in (self._volume_lbl, self._rate_lbl, self._minutes_lbl, self._cal_lbl):
            if lbl:
                lbl.setStyleSheet(
                    f"QLabel {{ color: {text}; }}"
                    f"QLabel:disabled {{ color: {t['text_dim']}; }}"
                )

        btn_ss = (
            f"QPushButton {{ background: {raised}; color: {text};"
            f"  border: 1px solid {border}; border-radius: 3px; padding: 2px 4px; }}"
            f"QPushButton:hover {{ border-color: {t['accent']}; }}"
            f"QPushButton:disabled {{ color: {muted}; border-color: {border}; }}"
        )
        for btn in (self._run_btn, self._pause_btn, self._clear_totals_btn,
                    self._refresh_btn, self._cal_run_btn):
            if btn:
                btn.setStyleSheet(btn_ss)

        # Stop is the one destructive control - give it the error colour. Needs
        # its own :disabled rule for the same reason as the inputs below.
        if self._stop_btn:
            self._stop_btn.setStyleSheet(
                f"QPushButton {{ background: {raised}; color: {t['error']};"
                f"  border: 1px solid {t['error']}; border-radius: 3px; padding: 2px 4px; }}"
                f"QPushButton:hover {{ background: {t['error']}; color: {t['widget_bg']}; }}"
                f"QPushButton:disabled {{ background: {raised}; color: {t['text_dim']};"
                f"  border-color: {border}; }}"
            )

        input_ss = (
            f"QAbstractSpinBox, QComboBox {{"
            f"  background: {t['bg_surface']}; color: {text}; border: 1px solid {border};"
            f"  border-radius: 3px; padding: 2px 6px; }}"
            f"QAbstractSpinBox:disabled, QComboBox:disabled {{"
            f"  background: {t['widget_bg']}; color: {t['text_dim']};"
            f"  border-color: {t['border']}; }}"
        )
        for box in (self._volume_spin, self._rate_spin, self._minutes_spin,
                    self._cal_spin, self._mode_combo):
            if box:
                box.setStyleSheet(input_ss)
        if self._reverse_check:
            self._reverse_check.setStyleSheet(f"color: {text};")

        self._update_volume_display()
        self._update_state_display()
        if self._graph:
            self._graph.set_theme(t)

    def _update_volume_display(self) -> None:
        t = self._t
        volume = self._volume
        colour = t["accent"] if self._running else t["text"]
        text = "—" if math.isnan(volume) else f"{volume:.2f}"

        if self._volume_value_lbl:
            self._volume_value_lbl.setText(text)
            self._volume_value_lbl.setStyleSheet(
                f"color: {colour};"
                f" background: {t['bg_surface']};"
                f" border: 2px solid {colour};"
                f" border-radius: 8px; padding: 8px;"
            )

    def _update_state_display(self) -> None:
        t = self._t
        if self._paused:
            label, colour = "Paused", t["text_muted"]
        elif self._running:
            label, colour = "Dispensing", t["dot_ok"]
        else:
            label, colour = "Idle", t["text_muted"]
        if self._state_lbl:
            self._state_lbl.setText(label)
            self._state_lbl.setStyleSheet(f"color: {colour}; font-size: 9pt; font-weight: bold;")
        if self._pause_btn:
            self._pause_btn.setText("Resume" if self._paused else "Pause")
            self._pause_btn.setEnabled(self._running or self._paused)
        if self._stop_btn:
            self._stop_btn.setEnabled(self._running or self._paused)


    def _wire(self) -> None:
        if self._mode_combo:
            self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        if self._run_btn:
            self._run_btn.clicked.connect(self._on_run)
        if self._pause_btn:
            self._pause_btn.clicked.connect(self._on_pause)
        if self._stop_btn:
            self._stop_btn.clicked.connect(self._client.stop)
        if self._clear_totals_btn:
            self._clear_totals_btn.clicked.connect(self._on_clear_totals)
        if self._refresh_btn:
            self._refresh_btn.clicked.connect(self._on_refresh)
        if self._cal_run_btn:
            self._cal_run_btn.clicked.connect(self._on_calibrate)
        self._on_mode_changed(0)


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

    def _on_volume(self, volume: float) -> None:
        self._volume = volume
        self._update_volume_display()
        self._graph.add_reading(volume)

    def _on_dispensing(self, running: bool) -> None:
        self._running = running
        if not running:
            self._paused = False
        self._graph.set_active(running)
        self._update_volume_display()
        self._update_state_display()

    def _on_stopped(self, volume: float) -> None:
        self._volume = volume
        self._running = False
        self._paused = False
        self._graph.set_active(False)
        self._update_volume_display()
        self._update_state_display()

    def _on_totals(self, net: float, absolute: float) -> None:
        if self._totals_lbl:
            self._totals_lbl.setText(f"Total: {net:.2f} ml  (abs {absolute:.2f})")

    def _on_limits(self, max_rate: float, volts: float) -> None:
        # "Metered max", not "max rate": MaxFlowRate is the fastest rate the
        # pump can *regulate* to, which is lower than the open-loop top speed
        # Continuous mode runs at. Labelling it "Max rate" made the two look
        # like one number.
        if self._limits_lbl:
            self._limits_lbl.setText(
                f"Metered max: {max_rate:.2f} ml/min    Pump: {volts:.2f} V"
            )
            self._limits_lbl.setToolTip(
                "Ceiling for Constant rate mode, reported by the pump and dependent\n"
                "on its calibration. Continuous mode ignores it and runs the motor\n"
                "at full speed."
            )
        # Cap the input at what the pump will actually accept, rather than
        # letting it reject the command. This is the only limit the widget
        # applies, and it comes from the device - nothing here assumes a model.
        if max_rate > 0 and self._rate_spin:
            self._rate_spin.setMaximum(max_rate)
            self._rate_spin.setToolTip(
                f"Up to {max_rate:.2f} ml/min - the fastest rate this pump can hold\n"
                "steady, which is below its top speed. Rises once calibrated."
            )

    def _on_error(self, msg: str) -> None:
        if self._conn_status_lbl:
            self._conn_status_lbl.setText(f"Error: {msg[:60]}")
            self._conn_status_lbl.setStyleSheet(
                f"color: {self._t['error']}; font-size: 9pt;"
            )

    def _on_mode_changed(self, index: int) -> None:
        """Show only the inputs the selected mode actually uses.

        Rows are hidden rather than greyed out: a visible-but-disabled spin box
        still invites clicking, and nothing on the form explains that Rate is
        dead until the mode is switched.
        """
        if index < 0 or index >= len(_MODES):
            return
        _, fields, hint = _MODES[index]
        for name, lbl, spin in (
            (_VOLUME,  self._volume_lbl,  self._volume_spin),
            (_RATE,    self._rate_lbl,    self._rate_spin),
            (_MINUTES, self._minutes_lbl, self._minutes_spin),
        ):
            used = name in fields
            if lbl:
                lbl.setVisible(used)
            if spin:
                spin.setEnabled(used)
                spin.setVisible(used)
        # One stable verb; the hint carries what this mode actually does.
        if self._run_btn:
            self._run_btn.setToolTip(hint)
        if self._mode_combo:
            self._mode_combo.setToolTip(hint)

        # Constant rate accepts an open-ended run (DC,rate,*); dose over time
        # divides by the duration, so zero is invalid there.
        if self._minutes_spin:
            if _RATE in fields:
                self._minutes_spin.setMinimum(0.0)
                self._minutes_spin.setSpecialValueText("until stopped")
                self._minutes_spin.setToolTip(
                    "How long to hold the rate. Lowest setting runs until Stop."
                )
            else:
                self._minutes_spin.setSpecialValueText("")
                self._minutes_spin.setMinimum(0.01)
                self._minutes_spin.setToolTip("Minutes to spread the dose over")

    def _on_run(self) -> None:
        index = self._mode_combo.currentIndex() if self._mode_combo else 0
        if index < 0 or index >= len(_MODES):
            return
        reverse = bool(self._reverse_check and self._reverse_check.isChecked())
        sign = -1.0 if reverse else 1.0
        volume = self._volume_spin.value() if self._volume_spin else 0.0
        minutes = self._minutes_spin.value() if self._minutes_spin else 0.0
        rate = self._rate_spin.value() if self._rate_spin else 0.0

        if index == 0:
            self._client.dispense(sign * volume)
        elif index == 1:
            self._client.dose_over_time(sign * volume, minutes)
        elif index == 2:
            self._client.set_flow_rate(sign * rate, minutes)
        else:
            self._client.dispense_continuously(reverse)

    def _on_pause(self) -> None:
        self._paused = not self._paused
        self._client.set_paused(self._paused)
        self._update_state_display()

    def _on_clear_totals(self) -> None:
        self._client.clear_total_volume()
        self._client.fetch_totals()

    def _on_refresh(self) -> None:
        self._client.fetch_totals()
        self._client.fetch_limits()

    def _on_calibrate(self) -> None:
        if self._cal_run_btn:
            self._cal_run_btn.setEnabled(False)
        self._client.calibrate(self._cal_spin.value() if self._cal_spin else 0.0)
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
