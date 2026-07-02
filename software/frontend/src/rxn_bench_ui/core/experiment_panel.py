"""Experiment runner panel - browse, run, and stop Python scripts; streams stdout/stderr live."""
from __future__ import annotations

import datetime
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from PySide6.QtCore import QFile, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QPlainTextEdit,
    QPushButton, QLineEdit, QVBoxLayout, QWidget,
)
from PySide6.QtUiTools import QUiLoader

_UI_DIR = Path(__file__).parent / "ui"

preferred_mdi_size = (700, 480)


class _ScriptRunner(QThread):
    """Runs a script in a subprocess and streams its output line by line."""

    line_ready = Signal(str)
    finished   = Signal(int)   # exit code

    def __init__(self, script_path: str) -> None:
        super().__init__()
        self._path   = script_path
        self._proc: subprocess.Popen | None = None

    def run(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [sys.executable, self._path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in self._proc.stdout:
                self.line_ready.emit(line.rstrip())
            self._proc.wait()
            self.finished.emit(self._proc.returncode)
        except Exception as e:
            self.line_ready.emit(f"[runner error] {e}")
            self.finished.emit(-1)

    def pause(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                os.kill(self._proc.pid, signal.SIGSTOP)
            except Exception:
                pass

    def resume(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                os.kill(self._proc.pid, signal.SIGCONT)
            except Exception:
                pass

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass


class ExperimentPanel(QWidget):
    """Loads experiment_panel.ui and manages the script lifecycle."""

    preferred_mdi_size = (580, 460)

    def __init__(self, t: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t       = t
        self._runner: _ScriptRunner | None = None
        self._paused  = False
        self._log_fh: TextIO | None = None

        loader = QUiLoader()
        f = QFile(str(_UI_DIR / "experiment_panel.ui"))
        f.open(QFile.ReadOnly)
        self._ui = loader.load(f, self)
        f.close()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ui)

        self._path_edit:        QLineEdit      = self._ui.findChild(QLineEdit,      "script_path_edit")
        self._browse_btn:       QPushButton    = self._ui.findChild(QPushButton,    "browse_btn")
        self._log_folder_edit:  QLineEdit      = self._ui.findChild(QLineEdit,      "log_folder_edit")
        self._log_folder_btn:   QPushButton    = self._ui.findChild(QPushButton,    "log_folder_btn")
        self._log_folder_clear: QPushButton    = self._ui.findChild(QPushButton,    "log_folder_clear_btn")
        self._play_btn:         QPushButton    = self._ui.findChild(QPushButton,    "play_btn")
        self._pause_btn:        QPushButton    = self._ui.findChild(QPushButton,    "pause_btn")
        self._stop_btn:         QPushButton    = self._ui.findChild(QPushButton,    "stop_btn")
        self._status_lbl:       QLabel         = self._ui.findChild(QLabel,         "run_status_lbl")
        self._log:              QPlainTextEdit = self._ui.findChild(QPlainTextEdit,  "log_output")

        self._apply_theme()
        self._wire()

    def _apply_theme(self) -> None:
        t = self._t
        self._ui.setStyleSheet(
            f"QWidget {{ background: {t['widget_bg']}; color: {t['text']}; }}"
            f"QPlainTextEdit {{ background: {t['bg']}; color: {t['text']};"
            f" font-family: monospace; border: 1px solid {t['border']};"
            f" border-radius: 4px; }}"
            f"QLabel#run_status_lbl {{ color: {t['text_muted']}; }}"
        )
        for btn in (self._browse_btn, self._log_folder_btn, self._log_folder_clear,
                    self._play_btn, self._pause_btn, self._stop_btn):
            if btn:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
                    f" border: 1px solid {t['border']}; border-radius: 4px; padding: 4px 12px; }}"
                    f"QPushButton:hover {{ border-color: {t['accent']}; }}"
                    f"QPushButton:disabled {{ color: {t['text_dim']}; }}"
                )
        if self._play_btn:
            self._play_btn.setStyleSheet(
                self._play_btn.styleSheet() +
                f"QPushButton:enabled {{ background: {t['accent']}; color: {t['accent_text']};"
                f" border-color: {t['accent']}; }}"
            )

    def _wire(self) -> None:
        self._browse_btn.clicked.connect(self._browse)
        self._log_folder_btn.clicked.connect(self._browse_log_folder)
        self._log_folder_clear.clicked.connect(self._clear_log_folder)
        self._play_btn.clicked.connect(self._play)
        self._pause_btn.clicked.connect(self._pause_resume)
        self._stop_btn.clicked.connect(self._stop)


    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Experiment Script", "",
            "Python scripts (*.py);;All files (*)",
        )
        if path:
            self._path_edit.setText(path)
            self._play_btn.setEnabled(True)
            self._status("Ready")
            self._log.clear()

    def _browse_log_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Log Output Folder",
            self._log_folder_edit.text() or str(Path.home()),
        )
        if folder:
            self._log_folder_edit.setText(folder)

    def _clear_log_folder(self) -> None:
        self._log_folder_edit.clear()

    def _play(self) -> None:
        script = self._path_edit.text().strip()
        if not script or not Path(script).exists():
            self._status("Script not found.")
            return

        self._log.clear()
        self._log.appendPlainText(f"$ {sys.executable} {script}\n")
        self._set_running(True)
        self._paused = False

        self._close_log_file()
        folder = self._log_folder_edit.text().strip()
        if folder:
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = Path(script).stem
            log_path = Path(folder) / f"{stem}_{ts}.log"
            try:
                self._log_fh = open(log_path, "w", encoding="utf-8")
                self._log_fh.write(f"# {sys.executable} {script}\n")
                self._log_fh.write(f"# started {datetime.datetime.now().isoformat()}\n\n")
                self._status(f"Running → {log_path.name}")
            except OSError as e:
                self._log_fh = None
                self._log.appendPlainText(f"[log file error: {e}]")

        self._runner = _ScriptRunner(script)
        self._runner.line_ready.connect(self._log.appendPlainText)
        self._runner.line_ready.connect(self._write_log_line)
        self._runner.finished.connect(self._on_finished)
        self._runner.start()

    def _pause_resume(self) -> None:
        if not self._runner:
            return
        if self._paused:
            self._runner.resume()
            self._paused = False
            self._pause_btn.setText("⏸  Pause")
            self._status("Running")
        else:
            self._runner.pause()
            self._paused = True
            self._pause_btn.setText("▶  Resume")
            self._status("Paused")

    def _stop(self) -> None:
        if self._runner:
            self._runner.stop()

    def _on_finished(self, code: int) -> None:
        self._set_running(False)
        self._paused = False
        self._pause_btn.setText("⏸  Pause")
        msg = "Finished" if code == 0 else f"Exited ({code})"
        self._status(msg)
        self._log.appendPlainText(f"\n[{msg}]")
        if self._log_fh:
            self._log_fh.write(f"\n# {msg} - {datetime.datetime.now().isoformat()}\n")
        self._close_log_file()


    def _set_running(self, running: bool) -> None:
        self._play_btn.setEnabled(not running and bool(self._path_edit.text()))
        self._pause_btn.setEnabled(running)
        self._stop_btn.setEnabled(running)
        self._browse_btn.setEnabled(not running)
        if running:
            self._status("Running")

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and refresh button and log styles."""
        self._t = t
        self._apply_theme()

    def closeEvent(self, event) -> None:
        """Flush and close the log file before the widget is destroyed."""
        self._close_log_file()
        super().closeEvent(event)

    def _write_log_line(self, line: str) -> None:
        if self._log_fh:
            try:
                self._log_fh.write(line + "\n")
                self._log_fh.flush()
            except OSError:
                pass

    def _close_log_file(self) -> None:
        if self._log_fh:
            try:
                self._log_fh.close()
            except OSError:
                pass
            self._log_fh = None

    def _status(self, text: str) -> None:
        if self._status_lbl:
            self._status_lbl.setText(text)
