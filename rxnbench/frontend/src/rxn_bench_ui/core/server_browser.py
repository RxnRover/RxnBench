"""Server browser dialog and per-server card widget."""
from __future__ import annotations

from pathlib import Path

import grpc
from PySide6.QtCore import QFile, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..discovery import DiscoveredServer, SilaDiscovery
from ..proto import sila_service_pb2 as _ss
from .. import themes

_UI_DIR = Path(__file__).parent / "ui"
_ASSET_DIR = Path(__file__).parent.parent / "assets"
_SS_PATH = (
    "/sila2.org.silastandard.core.silaservice.v1"
    ".SiLAService/Get_ImplementedFeatures"
)
_SCAN_TIMEOUT = 4.0



class _ScanWorker(QThread):
    finished = Signal(list, list)  # known, unknown

    def run(self) -> None:
        from .device_registry import is_recognized
        disc = SilaDiscovery(probe_features=True)
        rxnbench, unrecognized = disc.scan(timeout=_SCAN_TIMEOUT)
        # Promote any "unknown" server that matches the registry to the known list
        known = list(rxnbench)
        unknown = []
        for s in unrecognized:
            if is_recognized(s):
                known.append(s)
            else:
                unknown.append(s)
        self.finished.emit(known, unknown)


class _ManualProbeWorker(QThread):
    finished = Signal(list, list)

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port

    def run(self) -> None:
        server = DiscoveredServer(
            name=f"{self._host}:{self._port}",
            host=self._host,
            port=self._port,
            uuid=f"{self._host}:{self._port}",
        )
        channel = grpc.insecure_channel(f"{self._host}:{self._port}")
        try:
            raw = channel.unary_unary(_SS_PATH)(b"", timeout=3.0)
            resp = _ss.Get_ImplementedFeatures_Responses.FromString(bytes(raw))
            server.features = [item.value for item in resp.ImplementedFeatures]
        except Exception:
            pass
        finally:
            channel.close()
        from .device_registry import is_recognized
        if server.rxnbench_features or is_recognized(server):
            self.finished.emit([server], [])
        else:
            self.finished.emit([], [server])



class ServerCard(QFrame):
    """Island card for one discovered SiLA server, loaded from server_card.ui."""
    add_requested = Signal(object)  # DiscoveredServer

    def __init__(self, server: DiscoveredServer, t: dict, parent=None) -> None:
        super().__init__(parent)
        self._server = server

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "server_card.ui"))
        f.open(QFile.ReadOnly)
        inner = loader.load(f, self)
        f.close()

        # inner is QFrame(NoFrame) from the .ui - embed it, style self for the border
        wrap = QVBoxLayout(self)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(0)
        wrap.addWidget(inner)
        inner.setStyleSheet("background: transparent;")

        name_lbl: QLabel       = inner.findChild(QLabel,       "name_lbl")
        self._add_btn: QPushButton = inner.findChild(QPushButton,  "add_btn")
        uuid_lbl: QLabel       = inner.findChild(QLabel,       "uuid_lbl")
        # features_layout is a sub-layout; Qt parents it to the root widget
        self._feat_layout: QVBoxLayout = inner.findChild(QVBoxLayout, "features_layout")

        name_lbl.setText(server.name)
        uuid_lbl.setText(server.uuid)
        uuid_lbl.setStyleSheet(f"color: {t['text_dim']};")

        self._t         = t
        self._connected = False
        self._logo_lbl: QLabel | None = None
        self._fill_features(server, t)
        self._inject_logo(server, inner)
        self._apply_style(t)
        self._add_btn.clicked.connect(lambda: self.add_requested.emit(self._server))

    def _inject_logo(self, server: DiscoveredServer, inner: QWidget) -> None:
        """Insert a centred logo row between the name/button row and the feature list."""
        if not server.rxnbench_features:
            return
        from PySide6.QtCore import Qt

        SIZE = 100
        lbl = QLabel()
        lbl.setObjectName("rxnbench_logo")
        lbl.setFixedSize(SIZE, SIZE)
        lbl.setToolTip("Rxn Bench device")

        _logo_path = _ASSET_DIR / "rxnbench_logo.png"
        px = QPixmap(str(_logo_path))
        if not px.isNull():
            lbl.setPixmap(px.scaled(SIZE, SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            lbl.setStyleSheet(
                "background: #f97316; border-radius: 8px; color: #fff; font-weight: bold;"
            )
            lbl.setText("R")
            lbl.setAlignment(Qt.AlignCenter)

        logo_row = QHBoxLayout()
        logo_row.addStretch()
        logo_row.addWidget(lbl)
        logo_row.addStretch()

        # Insert after header_row (index 0), before features_layout (index 1)
        card_layout = inner.layout()
        if card_layout is not None:
            card_layout.insertLayout(1, logo_row)

        self._logo_lbl = lbl

    def _fill_features(self, server: DiscoveredServer, t: dict) -> None:
        features = server.rxnbench_features or [
            f for f in server.features
            if not f.startswith("org.silastandard/core/SiLAService")
        ]
        for feat in features:
            parts = feat.split("/")
            if len(parts) < 4:
                continue
            originator, category, cls_name, version = parts[:4]

            row = QHBoxLayout()
            row.setSpacing(6)
            cls_lbl = QLabel(cls_name)
            cls_lbl.setStyleSheet(f"color: {t['text']}; font-size: 10pt;")
            ver_lbl = QLabel(version)
            ver_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            row.addWidget(cls_lbl)
            row.addWidget(ver_lbl)
            row.addStretch()
            self._feat_layout.addLayout(row)

            orig_lbl = QLabel(f"{originator}/{category}")
            orig_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            self._feat_layout.addWidget(orig_lbl)

    def set_connected(self, connected: bool) -> None:
        """Update the card's visual state to reflect whether the device is open in the MDI area."""
        self._connected = connected
        if connected:
            self._apply_connected_style()
        else:
            self._add_btn.setText("+")
            self._apply_style(self._t)

    def _apply_connected_style(self) -> None:
        self._add_btn.setText("✓")
        self._add_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6;
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover   { background: #2563eb; }
            QPushButton:pressed { background: #1d4ed8; }
        """)

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and repaint all card labels and borders."""
        self._t = t
        # Update card border/background
        self._apply_card_frame(t)
        # Re-apply button state - if connected keep the blue check, otherwise re-style with new theme
        if self._connected:
            self._apply_connected_style()
        else:
            self._apply_add_btn_style(t)
        # Re-colour feature labels (skip the logo placeholder)
        for lbl in self.findChildren(QLabel):
            if lbl.objectName() == "rxnbench_logo":
                continue
            ss = lbl.styleSheet()
            new_ss = ""
            if "font-size: 9pt" in ss or "font-size: 8pt" in ss:
                size = "9pt" if "9pt" in ss else "8pt"
                new_ss = f"color: {t['text_muted']}; font-size: {size};"
            elif "font-size: 10pt" in ss:
                new_ss = f"color: {t['text']}; font-size: 10pt;"
            if new_ss:
                lbl.setStyleSheet(new_ss)

    def _apply_style(self, t: dict) -> None:
        self._apply_card_frame(t)
        self._apply_add_btn_style(t)

    def _apply_card_frame(self, t: dict) -> None:
        self.setObjectName("ServerCard")
        card_bg     = t.get("card_bg",     t["bg_raised"])
        card_border = t.get("card_border", t["border"])
        self.setStyleSheet(f"""
            QFrame#ServerCard {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 8px;
            }}
            QFrame#ServerCard:hover {{
                border-color: {t['accent']};
            }}
            QLabel {{ background: transparent; }}
        """)

    def _apply_add_btn_style(self, t: dict) -> None:
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t['accent']};
                color: {t['accent_text']};
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover   {{ background: {t['accent_dim']}; }}
            QPushButton:pressed {{ background: {t['accent_dim']}; }}
        """)



class _ManualEntryDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Server Manually")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Enter the server's IP address and gRPC port:"))

        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("Host"))
        self._host = QLineEdit()
        self._host.setPlaceholderText("192.168.1.42")
        host_row.addWidget(self._host, 1)
        layout.addLayout(host_row)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Port"))
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(50051)
        port_row.addWidget(self._port, 1)
        layout.addLayout(port_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def host(self) -> str:
        return self._host.text().strip()

    def port(self) -> int:
        return self._port.value()



class ServerBrowserDialog(QWidget):
    """
    Loads server_browser.ui and populates it with ServerCard islands.
    Emits device_requested(DiscoveredServer) when [+] is pressed on a card.
    Can be embedded in a layout or shown as a standalone window.
    """
    device_requested = Signal(object)  # DiscoveredServer

    def __init__(self, theme_name: str = "dark", parent=None) -> None:
        super().__init__(parent)
        self._t = themes.get(theme_name)
        self._known_cards:     list[ServerCard] = []
        self._unknown_cards:   list[ServerCard] = []
        self._scan_worker:     _ScanWorker | None = None
        self._manual_worker:   _ManualProbeWorker | None = None
        self._connected_uuids: set[str] = set()

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "server_browser.ui"))
        f.open(QFile.ReadOnly)
        self._ui = loader.load(f, self)
        f.close()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._ui)

        self._refresh_btn: QPushButton = self._ui.findChild(QPushButton, "refresh_btn")
        self._manual_btn:  QPushButton = self._ui.findChild(QPushButton, "manual_btn")
        self._status_lbl:  QLabel      = self._ui.findChild(QLabel,      "status_lbl")

        known_contents:   QWidget = self._ui.findChild(QWidget, "known_scroll_contents")
        unknown_contents: QWidget = self._ui.findChild(QWidget, "unknown_scroll_contents")
        self._known_layout:       QVBoxLayout = known_contents.layout()
        self._unknown_layout:     QVBoxLayout = unknown_contents.layout()
        self._known_placeholder:  QLabel = self._ui.findChild(QLabel, "known_placeholder")
        self._unknown_placeholder: QLabel = self._ui.findChild(QLabel, "unknown_placeholder")

        self._refresh_btn.clicked.connect(self._start_scan)
        self._manual_btn.clicked.connect(self._manual_entry)

        self._start_scan()

    def _start_scan(self) -> None:
        if self._scan_worker and self._scan_worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._clear_column(self._known_layout,   self._known_cards)
        self._clear_column(self._unknown_layout, self._unknown_cards)
        self._show_placeholder(self._known_placeholder,   "Scanning...")
        self._show_placeholder(self._unknown_placeholder, "Scanning...")
        self._status_lbl.setText(f"Scanning... ({int(_SCAN_TIMEOUT)}s)")
        self._scan_worker = _ScanWorker()
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_scan_done(self, rxnbench: list, unknown: list) -> None:
        self._populate(rxnbench, self._known_layout,   self._known_cards,   self._known_placeholder)
        self._populate(unknown,   self._unknown_layout, self._unknown_cards, self._unknown_placeholder)
        # Restore connected state for any devices that were connected before the refresh
        for uuid in self._connected_uuids:
            self._restore_connected(uuid)
        self._status_lbl.setText(
            f"Found {len(rxnbench)} known device(s), {len(unknown)} unknown server(s)."
        )
        self._refresh_btn.setEnabled(True)

    def _restore_connected(self, uuid: str) -> None:
        for card in self._known_cards + self._unknown_cards:
            if card._server.uuid == uuid:
                try:
                    card.set_connected(True)
                except RuntimeError:
                    pass
                return

    def _manual_entry(self) -> None:
        dlg = _ManualEntryDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        host, port = dlg.host(), dlg.port()
        if not host:
            return
        self._status_lbl.setText(f"Probing {host}:{port}...")
        self._manual_worker = _ManualProbeWorker(host, port)
        self._manual_worker.finished.connect(self._on_manual_done)
        self._manual_worker.start()

    def _on_manual_done(self, rxnbench: list, unknown: list) -> None:
        for s in rxnbench:
            self._add_card(s, self._known_layout, self._known_cards, self._known_placeholder)
        for s in unknown:
            self._add_card(s, self._unknown_layout, self._unknown_cards, self._unknown_placeholder)
        found = rxnbench + unknown
        self._status_lbl.setText(f"Added {found[0].name}." if found else "No response from server.")

    def _populate(self, servers, layout, cards, placeholder) -> None:
        if not servers:
            self._show_placeholder(placeholder, "No servers found.")
            return
        for s in servers:
            self._add_card(s, layout, cards, placeholder)

    def _add_card(self, server, layout, cards, placeholder) -> None:
        placeholder.hide()
        card = ServerCard(server, self._t)
        card.add_requested.connect(self.device_requested)
        layout.insertWidget(layout.count() - 1, card)  # before trailing stretch
        cards.append(card)

    def set_device_connected(self, uuid: str, connected: bool) -> None:
        """Mark the server card identified by uuid as connected or disconnected.

        Args:
            uuid: The SiLA server UUID to look up.
            connected: True to show the card as connected; False to reset it.
        """
        if connected:
            self._connected_uuids.add(uuid)
        else:
            self._connected_uuids.discard(uuid)
        for card in self._known_cards + self._unknown_cards:
            if card._server.uuid == uuid:
                try:
                    card.set_connected(connected)
                except RuntimeError:
                    pass  # Qt C++ object already deleted - safe to ignore
                return

    def _clear_column(self, layout, cards) -> None:
        for card in cards:
            layout.removeWidget(card)
            card.deleteLater()
        cards.clear()

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and propagate it to all server cards."""
        self._t = t
        for card in self._known_cards + self._unknown_cards:
            card.set_theme(t)

    @staticmethod
    def _show_placeholder(label: QLabel, text: str) -> None:
        label.setText(text)
        label.show()
