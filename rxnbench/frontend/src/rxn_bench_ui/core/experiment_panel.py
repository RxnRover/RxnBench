"""Experiment runner panel - browse, run, and stop Python scripts; streams stdout/stderr live."""
from __future__ import annotations

import datetime
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, TextIO

from PySide6.QtCore import QFile, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QLineEdit, QVBoxLayout, QWidget,
)
from PySide6.QtUiTools import QUiLoader

_UI_DIR = Path(__file__).parent / "ui"

preferred_mdi_size = (700, 480)


def _default_results_dir() -> Path:
    """Where experiment output goes when the user hasn't picked a folder.

    Frozen build: a `results/` folder next to the executable, so a lab
    operator finds their data right where the app lives. Source checkout:
    `results/` under the current working directory.
    """
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "results"


def _default_scripts_dir() -> Path:
    """Where the "Browse" dialog opens to find example experiment scripts.

    Frozen build: the `Scripts/` folder staged next to the executable by
    packaging/copy_workflows.py. Source checkout: the repo's
    rxnbench/backend/client/scripts/ directly, so devs see the same scripts
    without needing a build.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "Scripts"
    return Path(__file__).resolve().parents[4] / "backend" / "client" / "scripts"


def _workflow_manifest_path(script: str, results_dir: Path) -> Path:
    """Where a script's bench.workflow manifest lives, by convention.

    ``logs/<script-stem>_workflow.jsonl`` under the results folder - a
    script using bench.workflow should call
    ``bench.set_workflow_output(f"logs/{Path(__file__).stem}_workflow.jsonl")``
    to match, so this launcher can check it *before* starting the script.
    Not inside the per-run experiment folder start_experiment() creates:
    that folder is fresh every run, and resume needs a *stable* path.
    """
    return results_dir / "logs" / f"{Path(script).stem}_workflow.jsonl"


def _load_manifest_entries(manifest_path: Path) -> dict[str, dict[str, Any]]:
    """Replay a bench.workflow JSONL manifest into ``{step_id: latest row}``.

    Empty dict if the file doesn't exist or is unreadable. Deliberately
    doesn't import rxn_bench_client for this - it's a scripting library for
    experiment authors, not a frontend dependency, so this mirrors its tiny
    manifest format (one JSON object per line, later lines override earlier
    ones for the same step_id) directly instead.
    """
    if not manifest_path.exists():
        return {}
    entries: dict[str, dict[str, Any]] = {}
    try:
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                entries[row["step_id"]] = row
    except (OSError, json.JSONDecodeError, KeyError):
        return {}
    return entries


def _workflow_manifest_status(manifest_path: Path) -> tuple[str, dict[str, Any] | None]:
    """Classify *manifest_path* for the pre-launch resume/restart check.

    Returns one of:
      ("none", None)      - no (readable) manifest - a normal fresh run.
      ("pending", entry)  - entry is the first step that never reached
                             "done" - a stopped/failed run to resume.
      ("complete", None)  - every step is done - re-running as-is would do
                             nothing (remaining() skips anything done), so
                             this still needs a restart prompt, not "none".
    """
    entries = _load_manifest_entries(manifest_path)
    if not entries:
        return "none", None
    for entry in entries.values():
        if entry.get("status") != "done":
            return "pending", entry
    return "complete", None


def _resume_choice_from_role(role: QMessageBox.ButtonRole) -> str | None:
    """Map a clicked QMessageBox button's role to "resume"/"restart"/None.

    Split out from the dialog construction/exec() in
    ExperimentPanel._ask_resume_or_restart so this decision is testable
    without a Qt event loop.
    """
    if role == QMessageBox.AcceptRole:
        return "resume"
    if role == QMessageBox.DestructiveRole:
        return "restart"
    return None


class _ScriptRunner(QThread):
    """Runs a script in a subprocess and streams its output line by line."""

    line_ready = Signal(str)
    finished   = Signal(int)   # exit code

    def __init__(
        self,
        script_path: str,
        results_dir: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._path        = script_path
        self._results_dir = results_dir
        self._extra_env    = extra_env or {}
        self._proc: subprocess.Popen | None = None

    def _build_command(self) -> tuple[list[str], dict | None]:
        """Return the (argv, env) to launch the script with.

        In a packaged build `sys.executable` is this GUI app, not a Python
        interpreter, so `[sys.executable, script]` would just open a second UI
        (the script path is ignored as argv[1]). Re-exec ourselves in
        script-runner mode instead - the frozen bundle ships Python +
        rxn_bench_client, and the entrypoint runs RXN_BENCH_UI_RUN_SCRIPT. In a
        source checkout `sys.executable` is real Python, so run the script
        directly as before.
        """
        if getattr(sys, "frozen", False):
            return [sys.executable], {**os.environ, "RXN_BENCH_UI_RUN_SCRIPT": self._path}
        return [sys.executable, self._path], None

    def run(self) -> None:
        try:
            cmd, env = self._build_command()
            env = {**os.environ, **(env or {})}
            cwd: str | None = None
            if self._results_dir is not None:
                # Run the script with its results folder as the working
                # directory, and tell rxn_bench_client where relative
                # set_log_output() paths belong, so results land here rather
                # than wherever the app was launched from.
                cwd = str(self._results_dir)
                env["RXN_BENCH_RESULTS_DIR"] = cwd
            env.update(self._extra_env)
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                cwd=cwd,
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
        """Ask the script to exit cleanly; escalate to SIGTERM if it won't.

        SIGINT raises KeyboardInterrupt inside the script, so its
        `with RxnBenchClient()` block still runs and releases the experiment
        lock. A bare terminate() kills Python before that cleanup, stranding
        the lock on the gantry server (recoverable only via Force release).

        30s grace period, not a shorter one: close() parks the gantry (real,
        possibly slow motion) *before* releasing the lock, so a short grace
        period can let terminate() kill the process mid-park, after the
        motion but before the lock is released - confirmed 2026-08-13.
        """
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGINT)
            except Exception:
                pass

            def _escalate() -> None:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            threading.Timer(30.0, _escalate).start()


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

        if self._log_folder_edit is not None:
            # Show the default so operators know where results land when they
            # leave this blank; clearing it falls back here (see _play).
            self._log_folder_edit.setPlaceholderText(str(_default_results_dir()))

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
        # Prefer the currently-set script's folder (so re-browsing stays put),
        # then fall back to the bundled example scripts.
        current = self._path_edit.text().strip()
        if current and Path(current).parent.is_dir():
            start_dir = str(Path(current).parent)
        elif _default_scripts_dir().is_dir():
            start_dir = str(_default_scripts_dir())
        else:
            start_dir = ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Experiment Script", start_dir,
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

    def _resolve_results_dir(self) -> Path | None:
        """Pick the output folder and make sure it exists.

        The folder field wins if set; otherwise fall back to the app's default
        results/ dir. If neither is writable (e.g. installed under Program
        Files and elevated), drop back to the user's home so a run never fails
        just to save its output. Returns None only if even that fails.
        """
        folder = self._log_folder_edit.text().strip()
        preferred = Path(folder) if folder else _default_results_dir()
        for candidate in (preferred, Path.home() / "Rxn Bench" / "results"):
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate
            except OSError:
                continue
        return None

    def _play(self) -> None:
        script = self._path_edit.text().strip()
        if not script or not Path(script).exists():
            self._status("Script not found.")
            return

        # Check before touching any UI state, so a Cancel leaves everything
        # as it was.
        results_dir = self._resolve_results_dir()
        extra_env: dict[str, str] = {}
        if results_dir is not None:
            manifest_path = _workflow_manifest_path(script, results_dir)
            state, pending = _workflow_manifest_status(manifest_path)
            if state != "none":
                choice = self._ask_resume_or_restart(pending)
                if choice is None:
                    return  # operator cancelled - don't run anything
                if choice == "restart":
                    extra_env["RXN_BENCH_WORKFLOW_RESTART"] = "1"

        self._log.clear()
        self._log.appendPlainText(f"$ {sys.executable} {script}\n")
        self._set_running(True)
        self._paused = False

        self._close_log_file()
        if results_dir is not None:
            self._log.appendPlainText(f"# results -> {results_dir}\n")
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = Path(script).stem
            logs_dir = results_dir / "logs"
            log_path = logs_dir / f"{stem}_{ts}.log"
            try:
                logs_dir.mkdir(parents=True, exist_ok=True)
                self._log_fh = open(log_path, "w", encoding="utf-8")
                self._log_fh.write(f"# {sys.executable} {script}\n")
                self._log_fh.write(f"# started {datetime.datetime.now().isoformat()}\n\n")
                self._status(f"Running -> {log_path.name}")
            except OSError as e:
                self._log_fh = None
                self._log.appendPlainText(f"[log file error: {e}]")

        self._runner = _ScriptRunner(script, results_dir, extra_env)
        self._runner.line_ready.connect(self._log.appendPlainText)
        self._runner.line_ready.connect(self._write_log_line)
        self._runner.finished.connect(self._on_finished)
        self._runner.start()

    def _ask_resume_or_restart(self, pending: dict[str, Any] | None) -> str | None:
        """Prompt when running this script as-is wouldn't start a normal fresh run.

        Args:
            pending: First step that never reached "done" (a stopped/failed
                run to resume), or None if every step is already done.

        Returns "resume", "restart", or None if the operator cancelled (in
        which case the caller must not run the script at all).
        """
        if pending is not None:
            step_id = pending.get("step_id", "?")
            status  = pending.get("status", "?")
            error   = pending.get("error")
            text = (
                f"This script has an unfinished run from before - "
                f"step {step_id!r} was left {status}."
            )
            if error:
                text += f"\n\n{error}"
            text += "\n\nContinue where it left off, or start the whole workflow over?"
        else:
            text = (
                "This script already completed successfully last time - "
                "running it again as-is would skip every step and do nothing.\n\n"
                "Run it again from the start?"
            )

        box = QMessageBox(self)
        box.setWindowTitle("Resume workflow?" if pending is not None else "Run again?")
        box.setText(text)
        continue_btn = box.addButton("Continue", QMessageBox.AcceptRole) if pending is not None else None
        restart_btn = box.addButton(
            "Start Over" if pending is not None else "Run Again", QMessageBox.DestructiveRole
        )
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(continue_btn or restart_btn)
        box.exec()

        clicked = box.clickedButton()
        role = box.buttonRole(clicked) if clicked is not None else QMessageBox.RejectRole
        return _resume_choice_from_role(role)

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
            self._pause_btn.setText(">  Resume")
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
