"""Regression test: the Experiment Runner must not relaunch the GUI in a packaged build.

In a PyInstaller build `sys.executable` is the frozen UI app, not a Python
interpreter, so `subprocess.Popen([sys.executable, script])` opens a *second UI*
instead of running the script (the path is ignored as argv[1]). When frozen, the
runner must instead re-exec itself in script-runner mode via
RXN_BENCH_UI_RUN_SCRIPT, which the packaging entrypoint picks up and runs.
"""
import sys

from PySide6.QtWidgets import QApplication

from rxn_bench_ui.core.experiment_panel import _ScriptRunner

# _ScriptRunner is a QThread (QObject); ensure an application object exists.
_app = QApplication.instance() or QApplication([])


def test_dev_mode_runs_script_with_python_interpreter(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd, env = _ScriptRunner("/tmp/exp.py")._build_command()
    assert cmd == [sys.executable, "/tmp/exp.py"]
    assert env is None


def test_frozen_mode_reexecs_self_instead_of_opening_second_ui(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cmd, env = _ScriptRunner("/tmp/exp.py")._build_command()
    # The script path must NOT be handed to the frozen exe as an argument -
    # that is exactly what opened a second UI.
    assert cmd == [sys.executable]
    assert "/tmp/exp.py" not in cmd
    assert env is not None
    assert env["RXN_BENCH_UI_RUN_SCRIPT"] == "/tmp/exp.py"
