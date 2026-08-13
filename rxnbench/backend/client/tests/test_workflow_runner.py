"""Tests for WorkflowRunner: resume, audit trail, and unsafe-retry gating.

No servers or hardware - the runner only touches a JSONL manifest file.
"""
import json

import pytest

from rxn_bench_client.workflows.runner import StepNeedsConfirmation, WorkflowRunner, pending_step


def _read_manifest(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_step_records_done_on_success(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with runner.step("a", devices=["gantry"]):
            pass
    rows = _read_manifest(manifest)
    assert [r["status"] for r in rows] == ["running", "done"]
    assert rows[0]["devices"] == ["gantry"]
    assert runner.is_done("a")


def test_step_records_failed_and_reraises(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with pytest.raises(ValueError):
            with runner.step("a"):
                raise ValueError("boom")
    rows = _read_manifest(manifest)
    assert [r["status"] for r in rows] == ["running", "failed"]
    assert "boom" in rows[-1]["error"]
    assert not runner.is_done("a")


def test_remaining_skips_completed_steps_without_running_their_body(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with runner.step("well:A1"):
            pass

        seen = []
        for well in runner.remaining(["A1", "A2", "A3"], key=lambda w: f"well:{w}"):
            seen.append(well)
            with runner.step(f"well:{well}"):
                pass
    assert seen == ["A2", "A3"]  # A1's step body never re-ran


def test_resume_reloads_prior_manifest_and_skips_done_steps(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with runner.step("a"):
            pass
        with pytest.raises(RuntimeError):
            with runner.step("b"):
                raise RuntimeError("dispense interrupted")

    # Simulates a crashed/restarted script pointed at the same manifest.
    resumed = WorkflowRunner(manifest)
    try:
        assert resumed.is_done("a")
        assert not resumed.is_done("b")
    finally:
        resumed.close()


def test_reentering_a_failed_step_requires_confirmation(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with pytest.raises(RuntimeError):
            with runner.step("a"):
                raise RuntimeError("dispense interrupted")

        with pytest.raises(StepNeedsConfirmation):
            with runner.step("a"):
                pass


def test_confirm_retry_allows_rerunning_a_failed_step(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with pytest.raises(RuntimeError):
            with runner.step("a"):
                raise RuntimeError("dispense interrupted")

        with runner.step("a", confirm_retry=True):
            pass
    assert runner.is_done("a")


def test_idempotent_step_skips_confirmation_after_failure(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with pytest.raises(RuntimeError):
            with runner.step("a", idempotent=True):
                raise RuntimeError("read failed, nothing physical happened")

        with runner.step("a", idempotent=True):
            pass
    assert runner.is_done("a")


def test_crashed_mid_step_also_requires_confirmation(tmp_path):
    """A step stuck at "running" (process died before failed/done was
    written) must be treated the same as a failed step - we don't know
    whether its physical side effect happened."""
    manifest = tmp_path / "wf.jsonl"
    manifest.write_text(json.dumps({"step_id": "a", "status": "running"}) + "\n")

    runner = WorkflowRunner(manifest)
    try:
        assert not runner.is_done("a")
        with pytest.raises(StepNeedsConfirmation):
            with runner.step("a"):
                pass
    finally:
        runner.close()


def test_restart_ignores_prior_manifest_and_truncates_file(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with runner.step("a"):
            pass

    with WorkflowRunner(manifest, restart=True) as runner:
        assert not runner.is_done("a")  # prior history not loaded
        with runner.step("a"):  # no StepNeedsConfirmation - history is gone
            pass

    rows = _read_manifest(manifest)
    # Two rows for this one restarted attempt (running, done) - none left
    # over from the pre-restart attempt.
    assert [r["step_id"] for r in rows] == ["a", "a"]


def test_pending_step_returns_none_for_missing_or_fully_done_manifest(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    assert pending_step(manifest) is None  # doesn't exist yet

    with WorkflowRunner(manifest) as runner:
        with runner.step("a"):
            pass
    assert pending_step(manifest) is None  # everything recorded is done


def test_pending_step_returns_first_incomplete_step_in_order(tmp_path):
    manifest = tmp_path / "wf.jsonl"
    with WorkflowRunner(manifest) as runner:
        with runner.step("a"):
            pass
        with pytest.raises(RuntimeError):
            with runner.step("b"):
                raise RuntimeError("dispense interrupted")
        # "c" never even started.

    pending = pending_step(manifest)
    assert pending["step_id"] == "b"
    assert pending["status"] == "failed"
    assert "dispense interrupted" in pending["error"]


def test_relative_manifest_path_resolves_against_results_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RXN_BENCH_RESULTS_DIR", str(tmp_path))
    runner = WorkflowRunner("sub/wf.jsonl")
    try:
        with runner.step("a"):
            pass
    finally:
        runner.close()
    assert (tmp_path / "sub" / "wf.jsonl").exists()
