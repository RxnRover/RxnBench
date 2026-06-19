from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel

from chem_bench_ui.sila_client import SILA_PORT


class ServerInfoPanel(QWidget):
    """SiLA server overview: channel status + per-feature probe results."""

    def __init__(self):
        super().__init__()
        self._feat_rows: dict[str, QLabel] = {}   # feature name → badge label
        self._feat_vbox: QVBoxLayout | None = None
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(10)
        vbox.setContentsMargins(16, 16, 16, 16)

        conn_box = QGroupBox("SiLA Server")
        cl = QVBoxLayout(conn_box)
        self._host_lbl = QLabel("Server: —")
        cl.addWidget(self._host_lbl)
        self._conn_lbl = QLabel("Status:  Disconnected")
        self._conn_lbl.setStyleSheet("color:#666;")
        cl.addWidget(self._conn_lbl)
        vbox.addWidget(conn_box)

        feat_box = QGroupBox("Discovered Features")
        self._feat_vbox = QVBoxLayout(feat_box)
        self._feat_vbox.addStretch()   # rows inserted before this
        vbox.addWidget(feat_box)
        vbox.addStretch()

    # ── Public API ──────────────────────────────────────────────────────────

    def update_host(self, host: str):
        self._host_lbl.setText(f"Server:  {host}:{SILA_PORT}")

    def update_connection(self, ok: bool):
        if ok:
            self._conn_lbl.setText("Status:  Connected")
            self._conn_lbl.setStyleSheet("color:#4caf50;")
        else:
            self._conn_lbl.setText("Status:  Not connected — retrying…")
            self._conn_lbl.setStyleSheet("color:#888;")
            for badge in self._feat_rows.values():
                badge.setText("⟳  waiting")
                badge.setStyleSheet("color:#666; font-size:11px;")

    def update_features(self, found: list[str]):
        """Called after each probe cycle with the list of reachable feature names."""
        for name in found:
            if name not in self._feat_rows:
                self._add_row(name)

        found_set = set(found)
        for name, badge in self._feat_rows.items():
            if name in found_set:
                badge.setText("✓  available")
                badge.setStyleSheet("color:#4caf50; font-size:11px;")
            else:
                badge.setText("✗  not found")
                badge.setStyleSheet("color:#f44336; font-size:11px;")

    def update_feature_stream(self, name: str, ok: bool):
        """Called when a feature's live streams start or stop."""
        if name not in self._feat_rows:
            self._add_row(name)
        badge = self._feat_rows[name]
        if ok:
            badge.setText("● streaming")
            badge.setStyleSheet("color:#4caf50; font-size:11px;")
        else:
            badge.setText("⟳  stream lost")
            badge.setStyleSheet("color:#ff9800; font-size:11px;")

    # ── Internals ───────────────────────────────────────────────────────────

    def _add_row(self, name: str):
        row = QHBoxLayout()
        row.addWidget(QLabel(name))
        row.addStretch()
        badge = QLabel("⟳  probing")
        badge.setStyleSheet("color:#666; font-size:11px;")
        row.addWidget(badge)
        # Insert before the trailing stretch
        self._feat_vbox.insertLayout(self._feat_vbox.count() - 1, row)
        self._feat_rows[name] = badge
