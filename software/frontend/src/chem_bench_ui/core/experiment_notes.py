"""Experiment Notes core plugin — create and save experiment notes as .txt."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)


class ExperimentNotesPanel(QWidget):
    preferred_mdi_size = (440, 460)

    def __init__(self, t: dict, parent=None) -> None:
        super().__init__(parent)
        self._t = t
        self._path: Path | None = None
        self._dirty = False

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._title_lbl = QLabel("Untitled notes")
        btn_new     = QPushButton("New")
        btn_open    = QPushButton("Open…")
        btn_save    = QPushButton("Save")
        btn_save_as = QPushButton("Save As…")
        for btn in (btn_new, btn_open, btn_save, btn_save_as):
            btn.setFixedWidth(80)
        btn_new.clicked.connect(self._new)
        btn_open.clicked.connect(self._open_file)
        btn_save.clicked.connect(self._save)
        btn_save_as.clicked.connect(self._save_as)
        toolbar.addWidget(self._title_lbl, 1)
        toolbar.addWidget(btn_new)
        toolbar.addWidget(btn_open)
        toolbar.addWidget(btn_save)
        toolbar.addWidget(btn_save_as)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("Write experiment notes here…")
        self._editor.textChanged.connect(self._on_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(toolbar)
        layout.addWidget(self._editor)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_theme(self, t: dict) -> None:
        self._t = t

    # ------------------------------------------------------------------
    # Toolbar handlers
    # ------------------------------------------------------------------

    def _new(self) -> None:
        if self._dirty and not self._prompt_discard():
            return
        self._editor.clear()
        self._path = None
        self._dirty = False
        self._refresh_title()

    def _open_file(self) -> None:
        if self._dirty and not self._prompt_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Notes", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Open failed", str(exc))
            return
        self._editor.setPlainText(text)
        self._path = Path(path)
        self._dirty = False
        self._refresh_title()

    def _save(self) -> None:
        if self._path is None:
            self._save_as()
            return
        try:
            self._path.write_text(self._editor.toPlainText(), encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._dirty = False
        self._refresh_title()

    def _save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Notes As", "", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        self._path = Path(path)
        self._save()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_changed(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._refresh_title()

    def _refresh_title(self) -> None:
        name = self._path.name if self._path else "Untitled notes"
        self._title_lbl.setText(f"{'* ' if self._dirty else ''}{name}")

    def _prompt_discard(self) -> bool:
        """Return True if it is OK to discard unsaved changes."""
        reply = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            self._save()
            return not self._dirty
        return reply == QMessageBox.Discard
