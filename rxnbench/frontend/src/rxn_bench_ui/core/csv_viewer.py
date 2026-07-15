"""CSV Viewer core plugin - displays a CSV file in a live-updating table."""
from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


class CsvViewerPanel(QWidget):
    """MDI sub-window that displays a CSV file and polls it for live updates."""

    preferred_mdi_size = (720, 460)

    def __init__(self, t: dict, parent=None) -> None:
        """
        Args:
            t: Active theme dict.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._t = t
        self._path: Path | None = None
        self._mtime: float = 0.0

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._path_lbl = QLabel("No file selected.")
        self._path_lbl.setWordWrap(False)
        btn_open = QPushButton("Open…")
        btn_open.setFixedWidth(80)
        btn_open.clicked.connect(self._open_file)
        self._row_lbl = QLabel("")
        toolbar.addWidget(self._path_lbl, 1)
        toolbar.addWidget(self._row_lbl)
        toolbar.addWidget(btn_open)

        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(toolbar)
        layout.addWidget(self._table)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1500)

    # Public API

    def watch_file(self, path: str | Path) -> None:
        """Point the viewer at a file path and start watching it."""
        self._load(Path(path))

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict."""
        self._t = t

    # Internals

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        self._path = path
        self._path_lbl.setText(str(path))
        self._mtime = 0.0  # force reload
        self._poll()

    def _poll(self) -> None:
        if self._path is None or not self._path.exists():
            return
        mtime = self._path.stat().st_mtime
        if mtime == self._mtime:
            return
        self._mtime = mtime
        self._reload()

    def _reload(self) -> None:
        try:
            with open(self._path, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
        except Exception:
            return
        if not rows:
            return

        headers = rows[0]
        data = rows[1:]

        self._table.setColumnCount(len(headers))
        self._table.setRowCount(len(data))
        self._table.setHorizontalHeaderLabels(headers)

        for r, row in enumerate(data):
            for c in range(len(headers)):
                val = row[c] if c < len(row) else ""
                self._table.setItem(r, c, QTableWidgetItem(val))

        self._table.resizeColumnsToContents()
        self._table.scrollToBottom()
        n = len(data)
        self._row_lbl.setText(f"{n} row{'s' if n != 1 else ''}")
