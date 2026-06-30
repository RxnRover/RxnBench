"""Workspace loader panel — imports workspace YAML and renders a to-scale 2-D deck view."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import grpc
import yaml
from PySide6.QtCore import QFile, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QFileDialog, QInputDialog, QLabel, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ...discovery import DiscoveredServer
from ...core.generic_device import _ldelim, _encode_sstring

_UI_DIR = Path(__file__).parent / "ui"
_TIMEOUT = 6.0
_GANTRY_BASE = "/sila2.edu.iastate.ames.rxnbench.gantry.v0.Gantry"



@dataclass(frozen=True)
class _PlateSpec:
    rows: int
    cols: int
    spacing: float       # mm, centre-to-centre both axes
    diam: float          # mm, well diameter
    a1x: float           # mm, A1 centre from plate corner X
    a1y: float           # mm, A1 centre from plate corner Y
    width: float         # mm, overall plate footprint
    height: float        # mm, overall plate footprint


_PLATES: dict[str, _PlateSpec] = {
    "96_well_standard": _PlateSpec(
        rows=8,  cols=12, spacing=9.0,  diam=6.94,
        a1x=14.38, a1y=11.24, width=127.76, height=85.48,
    ),
    "24_well_standard": _PlateSpec(
        rows=4,  cols=6,  spacing=19.3, diam=15.62,
        a1x=15.63, a1y=13.79, width=127.76, height=85.48,
    ),
    "384_well_standard": _PlateSpec(
        rows=16, cols=24, spacing=4.5,  diam=3.3,
        a1x=12.13, a1y=8.99,  width=127.76, height=85.48,
    ),
}

_FALLBACK_SPEC = _PlateSpec(
    rows=8, cols=12, spacing=9.0, diam=6.94,
    a1x=14.38, a1y=11.24, width=127.76, height=85.48,
)

_PALETTE = [
    "#3b82f6", "#10b981", "#f59e0b",
    "#8b5cf6", "#ef4444", "#06b6d4",
]



def _encode_str_param(s: str) -> bytes:
    """Encode a single SiLA String command parameter (field 1)."""
    return _ldelim(1, _encode_sstring(s))


class _CmdWorker(QThread):
    done = Signal(str)   # "OK" or error message

    def __init__(self, host: str, port: int, path: str, payload: bytes) -> None:
        super().__init__()
        self._addr    = f"{host}:{port}"
        self._path    = path
        self._payload = payload

    def run(self) -> None:
        ch = grpc.insecure_channel(self._addr)
        try:
            ch.unary_unary(self._path)(self._payload, timeout=_TIMEOUT)
            self.done.emit("OK")
        except Exception as e:
            self.done.emit(f"Error: {e}")
        finally:
            ch.close()


class _ListWorker(QThread):
    done = Signal(str)   # raw response text or error

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._addr = f"{host}:{port}"

    def run(self) -> None:
        from ...core.generic_device import _decode_response
        ch = grpc.insecure_channel(self._addr)
        try:
            raw = ch.unary_unary(f"{_GANTRY_BASE}/ListWorkspaces")(b"", timeout=_TIMEOUT)
            self.done.emit(_decode_response(bytes(raw)))
        except Exception as e:
            self.done.emit(f"Error: {e}")
        finally:
            ch.close()



class WorkspaceCanvas(QWidget):
    """Renders a to-scale top-down view of a workspace YAML definition."""

    def __init__(self, t: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t           = t
        self._plates: list[dict] = []
        self._cal_ref     = ""
        self._active_well = ("", "")   # (plate_id, well_label) to highlight
        self._current_pos: tuple[float, float] | None = None  # gantry XY mm
        self.setMinimumSize(300, 200)

    def load(self, workspace: dict) -> None:
        self._plates  = workspace.get("plates", [])
        self._cal_ref = workspace.get("calibration_reference_well", "")
        self.update()

    def clear(self) -> None:
        self._plates  = []
        self._cal_ref = ""
        self._active_well = ("", "")
        self._current_pos = None
        self.update()

    def set_active_well(self, plate_id: str, well_label: str) -> None:
        self._active_well = (plate_id, well_label)
        self.update()

    def set_current_position(self, x: float, y: float) -> None:
        self._current_pos = (x, y)
        self.update()

    def set_theme(self, t: dict) -> None:
        self._t = t
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(self._t["bg_surface"]))
        if not self._plates:
            p.setPen(QColor(self._t["text_dim"]))
            p.setFont(QFont("sans-serif", 11))
            p.drawText(self.rect(), Qt.AlignCenter, "No workspace loaded.")
        else:
            self._paint_workspace(p)
        p.end()

    def _paint_workspace(self, p: QPainter) -> None:
        t   = self._t
        W   = self.width()
        H   = self.height()
        PAD = 40  # px around the content

        # Gather plate specs and bounding box (in mm)
        entries: list[tuple[dict, _PlateSpec]] = []
        for plate in self._plates:
            spec = _PLATES.get(plate.get("plate_type", ""), _FALLBACK_SPEC)
            entries.append((plate, spec))

        origins = [
            (p_["origin"].get("x", 0.0), p_["origin"].get("y", 0.0))
            for p_, _ in entries
        ]
        def plate_extents(plate: dict, spec: _PlateSpec) -> tuple[float, float, float, float]:
            ox_ = plate["origin"].get("x", 0.0)
            oy_ = plate["origin"].get("y", 0.0)
            if plate.get("orientation") == "rotated_90":
                return ox_ - spec.height, ox_, oy_, oy_ + spec.width
            return ox_, ox_ + spec.width, oy_, oy_ + spec.height

        extents = [plate_extents(pl, sp) for pl, sp in entries]
        min_x = min(e[0] for e in extents) - 15
        min_y = min(e[2] for e in extents) - 15
        max_x = max(e[1] for e in extents) + 15
        max_y = max(e[3] for e in extents) + 15

        span_x = max_x - min_x or 1
        span_y = max_y - min_y or 1

        avail_w = W - 2 * PAD
        avail_h = H - 2 * PAD
        scale   = min(avail_w / span_x, avail_h / span_y)   # px / mm

        rend_w  = span_x * scale
        rend_h  = span_y * scale
        ox_off  = PAD + (avail_w - rend_w) / 2
        oy_off  = PAD + (avail_h - rend_h) / 2

        def to_px(mmx: float, mmy: float) -> tuple[float, float]:
            # Y flipped so Y=min_y is at screen-bottom (conventional lab view)
            return (
                ox_off + (mmx - min_x) * scale,
                oy_off + rend_h - (mmy - min_y) * scale,
            )

        # Parse cal ref
        cal_plate_id, cal_well = "", ""
        if "/" in self._cal_ref:
            cal_plate_id, cal_well = self._cal_ref.split("/", 1)

        for i, (plate, spec) in enumerate(entries):
            pid         = plate.get("id", f"plate{i + 1}")
            ox          = plate["origin"].get("x", 0.0)
            oy          = plate["origin"].get("y", 0.0)
            rotated     = plate.get("orientation") == "rotated_90"
            color       = QColor(_PALETTE[i % len(_PALETTE)])

            def _well_gxy(pdx: float, pdy: float) -> tuple[float, float]:
                # Transform plate-local (pdx, pdy) to gantry XY, matching backend _apply_orientation.
                if rotated:
                    return ox - pdy, oy + pdx
                return ox + pdx, oy + pdy

            # Plate rectangle corners
            if rotated:
                sx1, sy1 = to_px(ox - spec.height, oy + spec.width)
                sx2, sy2 = to_px(ox,               oy)
            else:
                sx1, sy1 = to_px(ox,               oy + spec.height)
                sx2, sy2 = to_px(ox + spec.width,  oy)
            rect = QRectF(sx1, sy1, sx2 - sx1, sy2 - sy1)

            fill = QColor(color); fill.setAlphaF(0.12)
            p.fillRect(rect, fill)
            p.setPen(QPen(color, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, 3, 3)

            # Wells
            r_px = max(1.5, (spec.diam / 2) * scale)
            draw_wells = spec.rows * spec.cols <= 384

            for row in range(spec.rows):
                rl = chr(ord("A") + row)
                for col in range(spec.cols):
                    wlabel = f"{rl}{col + 1}"
                    gx, gy = _well_gxy(
                        spec.a1x + col * spec.spacing,
                        spec.a1y + row * spec.spacing,
                    )
                    wx, wy = to_px(gx, gy)
                    is_cal = (pid == cal_plate_id and wlabel == cal_well)

                    is_active = (
                        pid == self._active_well[0]
                        and wlabel == self._active_well[1]
                    )
                    if is_cal:
                        ac = QColor(t["accent"])
                        p.setBrush(QBrush(ac))
                        p.setPen(QPen(ac.darker(130), 1.5))
                        wr = r_px * 1.6
                    elif is_active:
                        ac = QColor(t.get("dot_ok", "#22c55e"))
                        p.setBrush(QBrush(ac))
                        p.setPen(QPen(ac.darker(130), 1.5))
                        wr = r_px * 1.6
                    elif draw_wells:
                        wf = QColor(color); wf.setAlphaF(0.35)
                        p.setBrush(QBrush(wf))
                        p.setPen(QPen(color, 0.8))
                        wr = r_px
                    else:
                        continue

                    p.drawEllipse(QRectF(wx - wr, wy - wr, wr * 2, wr * 2))

            # A1 label
            a1gx, a1gy = _well_gxy(spec.a1x, spec.a1y)
            a1x_px, a1y_px = to_px(a1gx, a1gy)
            p.setPen(QColor(t["text"]))
            p.setFont(QFont("sans-serif", max(6, int(scale * 3.5))))
            p.drawText(QRectF(a1x_px + r_px + 1, a1y_px - 8, 20, 12), Qt.AlignLeft, "A1")

            # Plate ID label in top-left of rect
            p.setPen(QColor(t["text"]))
            p.setFont(QFont("sans-serif", max(7, int(scale * 4.5)), QFont.Bold))
            p.drawText(QRectF(sx1 + 5, sy1 + 4, rect.width() - 10, 18), Qt.AlignLeft, pid)

        # Current gantry position crosshair
        if self._current_pos is not None:
            cx, cy = to_px(self._current_pos[0], self._current_pos[1])
            arm = 10
            cross_col = QColor(t.get("dot_warn", "#f59e0b"))
            p.setPen(QPen(cross_col, 2.0))
            p.drawLine(int(cx - arm), int(cy), int(cx + arm), int(cy))
            p.drawLine(int(cx), int(cy - arm), int(cx), int(cy + arm))
            p.setBrush(QBrush(cross_col))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(cx - 3, cy - 3, 6, 6))

        # Calibration reference label (bottom strip)
        if self._cal_ref:
            p.setPen(QColor(t["text_muted"]))
            p.setFont(QFont("sans-serif", 8))
            p.drawText(
                self.rect().adjusted(PAD, 0, -PAD, -6),
                Qt.AlignBottom | Qt.AlignLeft,
                f"▲ cal ref: {self._cal_ref}",
            )

        # Axis indicator (bottom-left)
        self._draw_axes(p, ox_off + 8, oy_off + rend_h - 8, t)

        # Scale bar (bottom-right)
        self._draw_scale_bar(p, scale, ox_off + rend_w, oy_off + rend_h, t)

    @staticmethod
    def _draw_axes(p: QPainter, ax: float, ay: float, t: dict) -> None:
        arm = 22
        col = QColor(t["text_dim"])
        p.setPen(QPen(col, 1.2))
        # X arrow
        p.drawLine(int(ax), int(ay), int(ax + arm), int(ay))
        p.drawLine(int(ax + arm), int(ay), int(ax + arm - 5), int(ay - 3))
        p.drawLine(int(ax + arm), int(ay), int(ax + arm - 5), int(ay + 3))
        # Y arrow (upward = positive Y in gantry)
        p.drawLine(int(ax), int(ay), int(ax), int(ay - arm))
        p.drawLine(int(ax), int(ay - arm), int(ax - 3), int(ay - arm + 5))
        p.drawLine(int(ax), int(ay - arm), int(ax + 3), int(ay - arm + 5))
        p.setFont(QFont("sans-serif", 7))
        p.setPen(col)
        p.drawText(QRectF(ax + arm + 2, ay - 6, 12, 12), "X")
        p.drawText(QRectF(ax - 8, ay - arm - 10, 12, 12), "Y")

    @staticmethod
    def _draw_scale_bar(p: QPainter, scale: float, rx: float, ry: float, t: dict) -> None:
        target_px = 70
        raw_mm    = target_px / scale
        magnitude = 10 ** math.floor(math.log10(max(raw_mm, 1e-9)))
        bar_mm    = next(
            (magnitude * f for f in (1, 2, 5, 10) if magnitude * f * scale >= target_px),
            magnitude * 10,
        )
        bar_px = bar_mm * scale
        bx0, bx1 = rx - bar_px, rx
        by        = ry + 16

        col = QColor(t["text_muted"])
        p.setPen(QPen(col, 1.5))
        p.drawLine(int(bx0), int(by), int(bx1), int(by))
        for bx in (bx0, bx1):
            p.drawLine(int(bx), int(by - 3), int(bx), int(by + 3))

        p.setPen(QColor(t["text_dim"]))
        p.setFont(QFont("sans-serif", 8))
        p.drawText(
            QRectF(bx0, by + 5, bar_px, 14), Qt.AlignCenter,
            f"{bar_mm:.0f} mm",
        )



class WorkspaceLoaderWidget(QWidget):
    """Workspace loader panel — edit/import YAML, send to server, preview canvas."""

    workspace_changed = Signal(dict)   # emits parsed workspace dict on each valid render

    def __init__(
        self,
        t: dict,
        server: DiscoveredServer | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._t      = t
        self._server = server
        self._worker: QThread | None = None

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "workspace_loader.ui"))
        f.open(QFile.ReadOnly)
        self._ui = loader.load(f, self)
        f.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ui)

        self._import_btn:   QPushButton    = self._ui.findChild(QPushButton,   "import_btn")
        self._load_btn:     QPushButton    = self._ui.findChild(QPushButton,   "load_btn")
        self._clear_btn:    QPushButton    = self._ui.findChild(QPushButton,   "clear_btn")
        self._apply_btn:    QPushButton    = self._ui.findChild(QPushButton,   "apply_btn")
        self._yaml_edit:    QPlainTextEdit = self._ui.findChild(QPlainTextEdit,"yaml_edit")
        self._file_lbl:     QLabel         = self._ui.findChild(QLabel,        "file_lbl")
        self._line_lbl:     QLabel         = self._ui.findChild(QLabel,        "line_count_lbl")
        self._status_lbl:   QLabel         = self._ui.findChild(QLabel,        "status_lbl")

        # Insert canvas into canvas_container
        container = self._ui.findChild(QWidget, "canvas_container")
        self._canvas = WorkspaceCanvas(t, container)
        container.layout().addWidget(self._canvas)

        self._apply_style()
        self._wire()

        if server is None:
            self._load_btn.setEnabled(False)
            self._load_btn.setToolTip("No server connected")

        self._status("")

    def _apply_style(self) -> None:
        t = self._t
        self._ui.setStyleSheet(
            f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}"
            f"QLabel {{ background: transparent; }}"
            f"QFrame#toolbar {{ background: {t['widget_bg']};"
            f" border-bottom: 1px solid {t['border']}; }}"
            f"QPlainTextEdit {{ background: {t['bg']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; }}"
            f"QLabel#file_lbl {{ color: {t['text_muted']}; }}"
            f"QLabel#editor_heading_lbl {{ color: {t['text_muted']}; }}"
            f"QLabel#line_count_lbl {{ color: {t['text_dim']}; }}"
        )
        for btn in (self._import_btn, self._load_btn, self._clear_btn, self._apply_btn):
            btn.setStyleSheet(
                f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
                f" border: 1px solid {t['border']}; border-radius: 4px;"
                f" padding: 3px 10px; }}"
                f"QPushButton:hover {{ border-color: {t['accent']}; }}"
                f"QPushButton:disabled {{ color: {t['text_dim']}; }}"
            )

    def _wire(self) -> None:
        self._import_btn.clicked.connect(self._on_import)
        self._load_btn.clicked.connect(self._on_load_by_name)
        self._clear_btn.clicked.connect(self._on_clear)
        self._apply_btn.clicked.connect(self._on_apply)
        self._yaml_edit.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        text = self._yaml_edit.toPlainText()
        lines = text.count("\n") + 1 if text.strip() else 0
        self._line_lbl.setText(f"{lines} lines" if lines else "")
        self._apply_btn.setEnabled(bool(text.strip()))
        # Live-update canvas as text changes
        self._try_render(text)

    def _try_render(self, text: str) -> None:
        try:
            ws = yaml.safe_load(text)
            if isinstance(ws, dict) and "plates" in ws:
                self._canvas.load(ws)
                self.workspace_changed.emit(ws)
        except Exception:
            pass  # Keep showing last valid render

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Workspace YAML", "", "YAML files (*.yaml *.yml);;All files (*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text()
            self._yaml_edit.setPlainText(text)
            self._file_lbl.setText(Path(path).name)
            self._status(f"Loaded {Path(path).name}")
        except Exception as e:
            self._status(f"Error reading file: {e}", error=True)

    def _on_load_by_name(self) -> None:
        if not self._server:
            return
        name, ok = QInputDialog.getText(
            self, "Load Workspace", "Workspace name (see ListWorkspaces for options):"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        self._status(f"Loading '{name}'…")
        payload = _encode_str_param(name)
        self._run(f"{_GANTRY_BASE}/SetWorkspace", payload,
                  ok_msg=f"Workspace '{name}' loaded.")

    def _on_apply(self) -> None:
        text = self._yaml_edit.toPlainText().strip()
        if not text:
            return
        self._try_render(text)
        if self._server:
            self._status("Sending workspace to server…")
            payload = _encode_str_param(text)
            self._run(f"{_GANTRY_BASE}/LoadWorkspaceYaml", payload,
                      ok_msg="Workspace applied.")
        else:
            self._status("Canvas updated (no server connected).")

    def _on_clear(self) -> None:
        self._yaml_edit.clear()
        self._file_lbl.setText("")
        self._canvas.clear()
        self._status("Workspace cleared.")

    def _run(self, path: str, payload: bytes, ok_msg: str) -> None:
        if not self._server:
            return
        self._apply_btn.setEnabled(False)
        self._load_btn.setEnabled(False)
        worker = _CmdWorker(self._server.host, self._server.port, path, payload)
        worker.done.connect(lambda msg: self._on_cmd_done(msg, ok_msg))
        worker.start()
        self._worker = worker

    def _on_cmd_done(self, msg: str, ok_msg: str) -> None:
        if msg == "OK":
            self._status(ok_msg)
        else:
            self._status(msg, error=True)
        self._apply_btn.setEnabled(bool(self._yaml_edit.toPlainText().strip()))
        if self._server:
            self._load_btn.setEnabled(True)

    def _status(self, text: str, error: bool = False) -> None:
        if not self._status_lbl:
            return
        self._status_lbl.setText(text)
        t = self._t
        if error:
            self._status_lbl.setStyleSheet(
                f"background: {t['error_bg']}; color: {t['error_text']};"
                f" border-top: 1px solid {t['error_border']}; padding: 6px;"
            )
        else:
            self._status_lbl.setStyleSheet(
                f"background: transparent; color: {t['text_muted']};"
                f" border-top: 1px solid {t['border']}; padding: 4px 6px;"
            )

    def set_theme(self, t: dict) -> None:
        self._t = t
        self._canvas.set_theme(t)
        self._apply_style()
        self._status(self._status_lbl.text())
