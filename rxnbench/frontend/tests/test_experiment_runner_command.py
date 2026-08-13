"""Regression test: the Experiment Runner must not relaunch the GUI in a packaged build.

In a PyInstaller build `sys.executable` is the frozen UI app, not a Python
interpreter, so `subprocess.Popen([sys.executable, script])` opens a *second UI*
instead of running the script (the path is ignored as argv[1]). When frozen, the
runner must instead re-exec itself in script-runner mode via
RXN_BENCH_UI_RUN_SCRIPT, which the packaging entrypoint picks up and runs.
"""
import json
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from rxn_bench_ui.core.experiment_panel import (
    _ScriptRunner,
    _resume_choice_from_role,
    _workflow_manifest_path,
    _workflow_manifest_status,
)

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


def test_script_runner_stores_extra_env():
    runner = _ScriptRunner("/tmp/exp.py", extra_env={"RXN_BENCH_WORKFLOW_RESTART": "1"})
    assert runner._extra_env == {"RXN_BENCH_WORKFLOW_RESTART": "1"}


def test_script_runner_extra_env_defaults_to_empty():
    assert _ScriptRunner("/tmp/exp.py")._extra_env == {}


# Workflow manifest convention + pre-launch status classification

def test_workflow_manifest_path_matches_rxn_bench_client_convention(tmp_path):
    path = _workflow_manifest_path("/anywhere/my_tour.py", tmp_path)
    assert path == tmp_path / "logs" / "my_tour_workflow.jsonl"


def test_workflow_manifest_status_none_when_manifest_missing(tmp_path):
    assert _workflow_manifest_status(tmp_path / "missing_workflow.jsonl") == ("none", None)


def test_workflow_manifest_status_pending_returns_first_incomplete_step_in_order(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    manifest.write_text(
        json.dumps({"step_id": "a", "status": "done"}) + "\n"
        + json.dumps({"step_id": "b", "status": "failed", "error": "dispense interrupted"}) + "\n"
    )
    state, pending = _workflow_manifest_status(manifest)
    assert state == "pending"
    assert pending["step_id"] == "b"
    assert pending["error"] == "dispense interrupted"


def test_workflow_manifest_status_complete_when_every_step_done(tmp_path):
    # Distinct from "none": a script that already fully completed must still
    # prompt before re-running, or bench.workflow.remaining() would skip
    # every step on the next run and the script would silently do nothing.
    manifest = tmp_path / "wf.jsonl"
    manifest.write_text(
        json.dumps({"step_id": "a", "status": "running"}) + "\n"
        + json.dumps({"step_id": "a", "status": "done"}) + "\n"
        + json.dumps({"step_id": "b", "status": "done"}) + "\n"
    )
    assert _workflow_manifest_status(manifest) == ("complete", None)


def test_workflow_manifest_status_none_for_unreadable_manifest(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    manifest.write_text("not valid json\n")
    assert _workflow_manifest_status(manifest) == ("none", None)


# Resume/restart dialog choice mapping (Qt-free - see _resume_choice_from_role)


def test_resume_choice_accept_role_means_resume():
    assert _resume_choice_from_role(QMessageBox.AcceptRole) == "resume"


def test_resume_choice_destructive_role_means_restart():
    assert _resume_choice_from_role(QMessageBox.DestructiveRole) == "restart"


def test_resume_choice_reject_role_means_cancelled():
    assert _resume_choice_from_role(QMessageBox.RejectRole) is None
