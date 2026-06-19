from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import QWidget

from chem_bench_ui.sila_client import ToolheadInfo
from chem_bench_ui.themes import get as _get_theme


class ToolheadDiagramWidget(QWidget):
    """2D top-down diagram of a toolhead's footprint, body centre, and tip.

    Shows things to scale within the widget canvas.  Drawn from a ToolheadInfo
    instance; call set_info() to update.
    """

    def __init__(self):
        super().__init__()
        self._info: ToolheadInfo | None = None
        self._theme: dict = _get_theme("dark")
        self.setMinimumSize(180, 180)

    def set_theme(self, t: dict):
        self._theme = t
        self.update()

    def set_info(self, info: ToolheadInfo | None):
        self._info = info
        self.update()

    def paintEvent(self, _):
        t = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(t['grid_bg']))

        info = self._info
        if info is None or not info.active or info.footprint_x <= 0:
            p.setPen(QColor(t['text_muted']))
            p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "No toolhead")
            return

        pad = 20
        # Scale so footprint fills ~60% of the canvas
        fx, fy = info.footprint_x, info.footprint_y
        scale = min((w - 2 * pad) / (fx * 2.5), (h - 2 * pad) / (fy * 2.5))

        # Canvas centre = carriage mount point
        cx = w / 2
        cy = h / 2

        # Body centre in canvas coords
        bcx = cx + info.offset_x * scale
        bcy = cy - info.offset_y * scale    # Y axis inverted on screen

        # Footprint rect (centred on body centre)
        fw = fx * scale
        fh = fy * scale
        frect_x = int(bcx - fw / 2)
        frect_y = int(bcy - fh / 2)

        # Footprint body
        fill = QColor(t['grid_foot'])
        fill.setAlpha(t['grid_foot_fill_alpha'])
        p.fillRect(frect_x, frect_y, int(fw), int(fh), fill)
        p.setPen(QPen(QColor(t['grid_foot']), 1))
        p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        p.drawRect(frect_x, frect_y, int(fw), int(fh))

        # Dimension labels
        p.setPen(QColor(t['text_muted']))
        p.setFont(QFont("monospace", 8))
        p.drawText(frect_x, frect_y - 12, f"{fx:.0f} mm")
        p.save()
        p.translate(frect_x - 10, frect_y + fh / 2)
        p.rotate(-90)
        p.drawText(0, 0, f"{fy:.0f} mm")
        p.restore()

        # Carriage mount point (small accent square)
        ms = 6
        p.setBrush(QBrush(QColor(t['accent'])))
        p.setPen(QPen(QColor(t['accent']), 1))
        p.drawRect(int(cx - ms / 2), int(cy - ms / 2), ms, ms)
        p.setFont(QFont("monospace", 8))
        p.setPen(QColor(t['accent']))
        p.drawText(int(cx) + 6, int(cy) + 4, "mount")

        # Tip cross (actual probe contact point)
        tipx = bcx + info.tip_x * scale
        tipy = bcy - info.tip_y * scale
        arm = 7
        p.setPen(QPen(QColor(t['grid_tip']), 2))
        p.drawLine(int(tipx) - arm, int(tipy), int(tipx) + arm, int(tipy))
        p.drawLine(int(tipx), int(tipy) - arm, int(tipx), int(tipy) + arm)
        p.setFont(QFont("monospace", 8))
        p.setPen(QColor(t['grid_tip']))
        p.drawText(int(tipx) + 8, int(tipy) + 4, "tip")

        # Offset arrow from mount to body centre (if non-zero)
        if abs(info.offset_x) > 0.5 or abs(info.offset_y) > 0.5:
            p.setPen(QPen(QColor(t['text_muted']), 1, Qt.PenStyle.DashLine))
            p.drawLine(int(cx), int(cy), int(bcx), int(bcy))
