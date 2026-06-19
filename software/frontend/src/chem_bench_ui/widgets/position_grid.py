from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import QWidget

from chem_bench_ui.sila_client import ToolheadInfo, X_MAX, Y_MAX
from chem_bench_ui.themes import get as _get_theme


class PositionGrid(QWidget):
    """Top-down XY view of the build plate. Click to send a move_to command."""

    move_requested = Signal(float, float)

    def __init__(self):
        super().__init__()
        self._x = self._y = 0.0
        self._target_x: float | None = None
        self._target_y: float | None = None
        self._homed = False
        self._toolhead: ToolheadInfo | None = None
        self._click_enabled = True
        self._theme: dict = _get_theme("dark")
        self.setMinimumSize(260, 260)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_theme(self, t: dict):
        self._theme = t
        self.update()

    def set_click_enabled(self, enabled: bool):
        self._click_enabled = enabled
        if not enabled:
            self._target_x = self._target_y = None  # clear lingering target from dev mode
        self.setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def set_position(self, x: float, y: float, homed: bool = False):
        self._x, self._y, self._homed = x, y, homed
        if self._target_x is not None:
            if abs(x - self._target_x) < 1.0 and abs(y - self._target_y) < 1.0:
                self._target_x = self._target_y = None
        self.update()

    def set_toolhead(self, info: "ToolheadInfo | None"):
        self._toolhead = info
        self.update()

    def _to_machine(self, px: float, py: float) -> tuple[float, float]:
        pad = 24
        area_w = self.width() - 2 * pad
        area_h = self.height() - 2 * pad
        x = (px - pad) / area_w * X_MAX
        y = (area_h - (py - pad)) / area_h * Y_MAX
        return max(0.0, min(X_MAX, x)), max(0.0, min(Y_MAX, y))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._click_enabled:
            x, y = self._to_machine(event.position().x(), event.position().y())
            self._target_x, self._target_y = x, y
            self.update()
            self.move_requested.emit(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 24

        area_w = w - 2 * pad
        area_h = h - 2 * pad

        t = self._theme
        # Grid background
        p.fillRect(pad, pad, area_w, area_h, QColor(t['grid_bg']))
        p.setPen(QPen(QColor(t['grid_line']), 1))
        for i in range(6):
            gx = pad + int(area_w * i / 5)
            gy = pad + int(area_h * i / 5)
            p.drawLine(gx, pad, gx, pad + area_h)
            p.drawLine(pad, gy, pad + area_w, gy)

        # Border
        p.setPen(QPen(QColor(t['grid_border']), 1))
        p.drawRect(pad, pad, area_w, area_h)

        # Gantry structure (top-down view)
        cy_g = int(pad + area_h - (self._y / Y_MAX) * area_h)
        rail_col = QColor(t['grid_rail'])
        # Y linear rails — two vertical bars on the left and right frame edges
        p.setPen(QPen(rail_col, 4))
        p.drawLine(pad, pad, pad, pad + area_h)
        p.drawLine(pad + area_w, pad, pad + area_w, pad + area_h)
        # X gantry beam — horizontal bar at current Y spanning the full X rail
        beam_col = QColor(t['grid_rail'])
        beam_col.setAlpha(160)
        p.setPen(QPen(beam_col, 2))
        p.drawLine(pad, cy_g, pad + area_w, cy_g)
        # Carriage blocks (where the gantry rides on the Y rails)
        bw, bh = 8, 14
        p.setBrush(QBrush(QColor(t['grid_carriage'])))
        p.setPen(QPen(QColor(t['grid_border']), 1))
        p.drawRect(pad - bw // 2, cy_g - bh // 2, bw, bh)
        p.drawRect(pad + area_w - bw // 2, cy_g - bh // 2, bw, bh)

        # Axis labels
        p.setPen(QColor(t['grid_text']))
        p.setFont(QFont("monospace", 8))
        p.drawText(pad, h - 6, "0")
        p.drawText(w - 36, h - 6, f"{X_MAX:.0f}")
        p.drawText(2, pad + 10, f"{Y_MAX:.0f}")
        p.drawText(2, h - pad - 2, "0")
        p.drawText(w // 2 - 6, h - 6, "X")
        p.drawText(2, h // 2, "Y")

        # Toolhead footprint rectangle
        th = self._toolhead
        if th and th.active and th.footprint_x > 0 and th.footprint_y > 0:
            fp_w = (th.footprint_x / X_MAX) * area_w
            fp_h = (th.footprint_y / Y_MAX) * area_h
            # Carriage pixel position
            cx0 = pad + (self._x / X_MAX) * area_w
            cy0 = pad + area_h - (self._y / Y_MAX) * area_h
            # Body centre = carriage + body offset
            bcx = cx0 + (th.offset_x / X_MAX) * area_w
            bcy = cy0 - (th.offset_y / Y_MAX) * area_h
            # Actual tip = body centre + within-body tip offset
            tipx = bcx + (th.tip_x / X_MAX) * area_w
            tipy = bcy - (th.tip_y / Y_MAX) * area_h
            # Footprint rectangle centred on body centre
            fx = int(bcx - fp_w / 2)
            fy = int(bcy - fp_h / 2)
            fill = QColor(t['grid_foot'])
            fill.setAlpha(t['grid_foot_fill_alpha'])
            p.fillRect(fx, fy, int(fp_w), int(fp_h), fill)
            p.setPen(QPen(QColor(t['grid_foot']), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(fx, fy, int(fp_w), int(fp_h))
            # Tip cross (where the probe actually touches)
            p.setPen(QPen(QColor(t['grid_tip']), 1))
            arm = 5
            p.drawLine(int(tipx) - arm, int(tipy), int(tipx) + arm, int(tipy))
            p.drawLine(int(tipx), int(tipy) - arm, int(tipx), int(tipy) + arm)

        # Target crosshair (click-to-move destination)
        if self._target_x is not None:
            tx = int(pad + (self._target_x / X_MAX) * area_w)
            ty = int(pad + area_h - (self._target_y / Y_MAX) * area_h)
            p.setPen(QPen(QColor(t['accent2']), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(tx - 9, ty - 9, 18, 18)
            p.setPen(QPen(QColor(t['accent2']), 1))
            p.drawLine(tx - 14, ty, tx - 6, ty)
            p.drawLine(tx + 6,  ty, tx + 14, ty)
            p.drawLine(tx, ty - 14, tx, ty - 6)
            p.drawLine(tx, ty + 6,  tx, ty + 14)

        # Carriage dot — Y=0 at front/bottom, increases toward back/top
        cx = pad + (self._x / X_MAX) * area_w
        cy = pad + area_h - (self._y / Y_MAX) * area_h

        # Drop shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 80)))
        p.drawEllipse(int(cx) - 6, int(cy) - 4, 12, 12)

        color = QColor(t['dot_ok']) if self._homed else QColor(t['dot_warn'])
        p.setBrush(QBrush(color))
        p.setPen(QPen(QColor(t['text']), 1.5))
        p.drawEllipse(int(cx) - 5, int(cy) - 5, 10, 10)
        p.end()
