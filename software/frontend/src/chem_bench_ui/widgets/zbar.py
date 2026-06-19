from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget

from chem_bench_ui.sila_client import ToolheadInfo, Z_MAX
from chem_bench_ui.themes import get as _get_theme


class ZBar(QWidget):
    """Vertical indicator showing current Z height from 0 (bed) to Z_MAX (fully raised)."""

    def __init__(self):
        super().__init__()
        self._z = 0.0
        self._homed = False
        self._toolhead: ToolheadInfo | None = None
        self._theme: dict = _get_theme("dark")
        self.setFixedWidth(52)
        self.setMinimumHeight(260)

    def set_theme(self, t: dict):
        self._theme = t
        self.update()

    def set_z(self, z: float, homed: bool = False):
        self._z, self._homed = z, homed
        self.update()

    def set_toolhead(self, info: "ToolheadInfo | None"):
        self._toolhead = info
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 24
        track_top = pad
        track_bot = h - pad
        track_h   = track_bot - track_top
        track_x   = w // 2 - 6
        track_w   = 12

        t = self._theme
        # Track background
        p.fillRect(track_x, track_top, track_w, track_h, QColor(t['grid_bg']))
        p.setPen(QPen(QColor(t['grid_border']), 1))
        p.drawRect(track_x, track_top, track_w, track_h)

        # Filled portion (bottom = Z=0, top = Z_MAX)
        frac   = max(0.0, min(1.0, self._z / Z_MAX)) if Z_MAX > 0 else 0.0
        fill_h = int(frac * track_h)
        fill_y = track_bot - fill_h
        color  = QColor(t['dot_ok']) if self._homed else QColor(t['dot_warn'])
        if fill_h > 0:
            p.fillRect(track_x + 1, fill_y, track_w - 2, fill_h, color)

        # Marker line at current Z
        p.setPen(QPen(color.lighter(140), 2))
        p.drawLine(track_x - 3, fill_y, track_x + track_w + 3, fill_y)

        # Tick marks at 25 % intervals
        p.setPen(QPen(QColor(t['grid_line']), 1))
        for frac_tick in (0.25, 0.5, 0.75):
            ty = int(track_bot - frac_tick * track_h)
            p.drawLine(track_x, ty, track_x + track_w, ty)

        # End labels
        p.setFont(QFont("monospace", 8))
        p.setPen(QColor(t['grid_text']))
        p.drawText(0, track_top - 2, w, 12, Qt.AlignmentFlag.AlignHCenter, f"{Z_MAX:.0f}")
        p.drawText(0, track_bot + 2, w, 12, Qt.AlignmentFlag.AlignHCenter, "0")

        # Axis label
        p.setPen(QColor(t['text_muted']))
        p.setFont(QFont("monospace", 9))
        p.drawText(0, h // 2 - 6, w, 12, Qt.AlignmentFlag.AlignHCenter, "Z")

        # Current value floating near the marker (clamped to stay in view)
        p.setPen(QColor(t['text']))
        p.setFont(QFont("monospace", 8))
        val_y = max(track_top + 12, min(fill_y - 2, track_bot - 12))
        p.drawText(0, val_y, w, 12, Qt.AlignmentFlag.AlignHCenter, f"{self._z:.1f}")

        # Toolhead tip and engage depth markers
        th = self._toolhead
        if th and th.active and th.tip_offset_z > 0:
            tip_z  = self._z - th.tip_offset_z
            tip_y  = int(track_bot - (tip_z / Z_MAX) * track_h)
            # Tip line — amber
            p.setPen(QPen(QColor("#ffb300"), 2))
            p.drawLine(track_x - 4, tip_y, track_x + track_w + 4, tip_y)
            if th.z_engage > 0:
                eng_z = tip_z - th.z_engage
                eng_y = int(track_bot - (eng_z / Z_MAX) * track_h)
                # Engage bracket — dashed red
                pen = QPen(QColor("#ef5350"), 1, Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.drawLine(track_x + track_w + 4, tip_y,
                           track_x + track_w + 4, eng_y)
                p.setPen(QPen(QColor("#ef5350"), 2))
                p.drawLine(track_x - 4, eng_y, track_x + track_w + 4, eng_y)

        p.end()
