"""Tests for RxnBenchClient - session management, at_well, pause/stop, CSV logging.

No servers or hardware: instruments are lightweight fakes, SilaClient is
monkeypatched out, and time.sleep is disabled. Mirrors the fake-based style of
the gantry/pH backend suites.
"""
import csv
import json
import pathlib

import pytest

import rxn_bench_client.client as client_module
from rxn_bench_client.client import ExperimentStopped, RxnBenchClient
from rxn_bench_client.instruments.motion import Gantry


class _FakeGantry:
    """Records the at_well motion sequence and serves experiment state."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.states: list[str] = []  # popped left-to-right; last value repeats

    def move_to_well(self, well, override_unvalidated=False):
        self.calls.append(("move_to_well", well, override_unvalidated))

    def engage_tool(self):
        self.calls.append(("engage_tool",))

    def disengage_tool(self):
        self.calls.append(("disengage_tool",))

    def acquire_experiment_lock(self):
        self.calls.append(("acquire_experiment_lock",))

    def release_experiment_lock(self):
        self.calls.append(("release_experiment_lock",))

    def get_experiment_state(self):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


class _FakePHProbe:
    """Instrument with no experiment-lock support (like PHProbe)."""

    def __init__(self):
        pass


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(client_module.time, "sleep", lambda *_a, **_k: None)


@pytest.fixture
def bench():
    b = RxnBenchClient()
    yield b
    b.close()


def _attach_gantry(bench, states=("running",)):
    g = _FakeGantry()
    g.states = list(states)
    bench.gantry = g
    bench._lock_holder = g
    return g


# at_well context manager

def test_at_well_requires_gantry(bench):
    with pytest.raises(RuntimeError, match="requires a gantry"):
        with bench.at_well("plate1/A1"):
            pass


def test_at_well_moves_engages_runs_body_then_disengages(bench):
    g = _attach_gantry(bench)
    order = []
    with bench.at_well("plate1/A3"):
        order.append("body")
    assert [c[0] for c in g.calls if c[0] != "acquire_experiment_lock"] == [
        "move_to_well", "engage_tool", "disengage_tool",
    ]
    assert ("move_to_well", "plate1/A3", False) in g.calls
    assert order == ["body"]


def test_at_well_forwards_override_unvalidated(bench):
    """Mock/dev escape hatch for placeholder toolhead geometry - at_well must
    forward the flag or scripts can't use it with an uncalibrated probe."""
    g = _attach_gantry(bench)
    with bench.at_well("plate1/A1", override_unvalidated=True):
        pass
    assert ("move_to_well", "plate1/A1", True) in g.calls


def test_at_well_disengages_even_when_body_raises(bench):
    g = _attach_gantry(bench)
    with pytest.raises(ValueError):
        with bench.at_well("plate1/A1"):
            raise ValueError("probe fault")
    assert ("disengage_tool",) in g.calls


def test_at_well_clears_current_well_after_exit(bench):
    _attach_gantry(bench)
    with bench.at_well("plate1/B2"):
        assert bench._current_well == "plate1/B2"
    assert bench._current_well is None


# check_pause_stop

def test_check_pause_stop_noop_without_lock_holder(bench):
    bench.check_pause_stop()  # no gantry connected -> nothing to check


def test_check_pause_stop_passes_while_running(bench):
    _attach_gantry(bench, states=("running",))
    bench.check_pause_stop()


def test_check_pause_stop_raises_on_stop_requested(bench):
    _attach_gantry(bench, states=("stop_requested",))
    with pytest.raises(ExperimentStopped):
        bench.check_pause_stop()


def test_check_pause_stop_waits_through_pause_then_resumes(bench):
    _attach_gantry(bench, states=("paused", "paused", "running"))
    bench.check_pause_stop()  # returns once the state leaves "paused"


def test_check_pause_stop_stop_during_pause_raises(bench):
    _attach_gantry(bench, states=("paused", "stop_requested"))
    with pytest.raises(ExperimentStopped):
        bench.check_pause_stop()


# CSV logging

def test_log_without_output_raises(bench):
    with pytest.raises(RuntimeError, match="set_log_output"):
        bench.log(ph=7.0)


def test_log_discovers_columns_from_first_call(bench, tmp_path):
    out = tmp_path / "results.csv"
    bench.set_log_output(out)
    bench.log(ph=7.21, temp=22.1)
    bench.log(ph=7.19, temp=22.3)
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0].keys()) == ["timestamp", "ph", "temp"]
    assert rows[0]["ph"] == "7.21" and rows[1]["temp"] == "22.3"


def test_set_log_output_does_not_overwrite_existing_file(bench, tmp_path):
    """A results.csv from a previous run must survive a re-run with the same name."""
    out = tmp_path / "results.csv"
    out.write_text("previous run's data\n")

    bench.set_log_output(out)
    bench.log(ph=7.0)

    assert out.read_text() == "previous run's data\n"
    new_out = tmp_path / "results_1.csv"
    assert new_out.exists()
    rows = list(csv.DictReader(new_out.open()))
    assert rows[0]["ph"] == "7.0"


def test_set_log_output_increments_past_multiple_existing_files(bench, tmp_path):
    (tmp_path / "results.csv").write_text("run 1\n")
    (tmp_path / "results_1.csv").write_text("run 2\n")

    bench.set_log_output(tmp_path / "results.csv")
    bench.log(ph=7.0)

    assert (tmp_path / "results.csv").read_text() == "run 1\n"
    assert (tmp_path / "results_1.csv").read_text() == "run 2\n"
    assert (tmp_path / "results_2.csv").exists()


def test_log_with_explicit_columns_writes_header_up_front(bench, tmp_path):
    out = tmp_path / "results.csv"
    bench.set_log_output(out, columns=["ph"])
    assert out.read_text().strip() == "timestamp,ph"
    bench.log(ph=6.5, ignored="dropped")  # extrasaction="ignore"
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["ph"] == "6.5" and "ignored" not in rows[0]


def test_log_skips_row_when_write_fails(bench, tmp_path, capsys):
    """A dropped network share or similar I/O failure must not kill the run."""
    out = tmp_path / "results.csv"
    bench.set_log_output(out, columns=["ph"])

    def _boom(*_a, **_kw):
        raise OSError("disk gone")
    bench._log_writer.writerow = _boom

    bench.log(ph=7.0)  # must not raise

    assert "Could not write log row, skipping" in capsys.readouterr().out


def test_log_recovers_once_writes_work_again(bench, tmp_path):
    out = tmp_path / "results.csv"
    bench.set_log_output(out, columns=["ph"])

    real_writerow = bench._log_writer.writerow
    calls = {"n": 0}

    def _flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk gone")
        return real_writerow(*a, **kw)
    bench._log_writer.writerow = _flaky

    bench.log(ph=7.0)  # dropped
    bench.log(ph=7.1)  # succeeds

    rows = list(csv.DictReader(out.open()))
    assert [r["ph"] for r in rows] == ["7.1"]


def test_log_inside_at_well_includes_well_column(bench, tmp_path):
    _attach_gantry(bench)
    out = tmp_path / "results.csv"
    bench.set_log_output(out)
    with bench.at_well("plate1/C4"):
        bench.log(ph=7.0)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["well"] == "plate1/C4"


def test_log_creates_parent_directories(bench, tmp_path):
    out = tmp_path / "deep" / "nested" / "results.csv"
    bench.set_log_output(out)
    bench.log(ph=7.0)
    assert out.exists()


def test_relative_path_resolves_against_results_dir_env(bench, tmp_path, monkeypatch):
    monkeypatch.setenv("RXN_BENCH_RESULTS_DIR", str(tmp_path))
    bench.set_log_output("results.csv")
    bench.log(ph=7.0)
    assert (tmp_path / "results.csv").exists()


def test_relative_path_falls_back_to_cwd_without_env(bench, tmp_path, monkeypatch):
    monkeypatch.delenv("RXN_BENCH_RESULTS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    bench.set_log_output("results.csv")
    bench.log(ph=7.0)
    assert (tmp_path / "results.csv").exists()


# Workflow (bench.workflow / set_workflow_output)

def test_workflow_without_output_raises(bench):
    with pytest.raises(RuntimeError, match="set_workflow_output"):
        bench.workflow


def test_workflow_step_tracks_status(bench, tmp_path):
    bench.set_workflow_output(tmp_path / "wf.jsonl")
    with bench.workflow.step("a"):
        pass
    assert bench.workflow.is_done("a")


def test_workflow_manifest_persists_across_a_new_client_session(bench, tmp_path):
    manifest = tmp_path / "wf.jsonl"
    bench.set_workflow_output(manifest)
    with bench.workflow.step("a"):
        pass
    bench.close()

    resumed = RxnBenchClient()
    resumed.set_workflow_output(manifest)
    try:
        assert resumed.workflow.is_done("a")
    finally:
        resumed.close()


def test_close_closes_the_workflow_manifest(bench, tmp_path):
    bench.set_workflow_output(tmp_path / "wf.jsonl")
    workflow = bench.workflow
    bench.close()
    assert workflow._file.closed


def test_set_workflow_output_resumes_by_default(bench, tmp_path):
    manifest = tmp_path / "wf.jsonl"
    bench.set_workflow_output(manifest)
    with bench.workflow.step("a"):
        pass
    bench.set_workflow_output(manifest)  # reconfigure, same path
    assert bench.workflow.is_done("a")


def test_set_workflow_output_restart_true_ignores_prior_manifest(bench, tmp_path):
    manifest = tmp_path / "wf.jsonl"
    bench.set_workflow_output(manifest)
    with bench.workflow.step("a"):
        pass
    bench.set_workflow_output(manifest, restart=True)
    assert not bench.workflow.is_done("a")


def test_set_workflow_output_respects_restart_env_var(bench, tmp_path, monkeypatch):
    manifest = tmp_path / "wf.jsonl"
    bench.set_workflow_output(manifest)
    with bench.workflow.step("a"):
        pass

    monkeypatch.setenv("RXN_BENCH_WORKFLOW_RESTART", "1")
    bench.set_workflow_output(manifest)
    assert not bench.workflow.is_done("a")


def test_set_workflow_output_explicit_restart_overrides_env_var(bench, tmp_path, monkeypatch):
    manifest = tmp_path / "wf.jsonl"
    bench.set_workflow_output(manifest)
    with bench.workflow.step("a"):
        pass

    monkeypatch.setenv("RXN_BENCH_WORKFLOW_RESTART", "1")
    bench.set_workflow_output(manifest, restart=False)
    assert bench.workflow.is_done("a")


# connect() / close() session wiring

class _FakeSilaClient:
    instances: list = []

    def __init__(self, host, port, insecure):
        self.host, self.port, self.insecure = host, port, insecure
        self.closed = False
        _FakeSilaClient.instances.append(self)

    def close(self):
        self.closed = True


class _LockCapableInstrument:
    def __init__(self, sila):
        self.sila = sila
        self.lock_acquired = False
        self.lock_released = False
        self.parked = False
        self.workspace_yaml = ""
        self.position = (1.0, 2.0, 3.0)
        self.position_raises = False

    def acquire_experiment_lock(self):
        self.lock_acquired = True

    def release_experiment_lock(self):
        self.lock_released = True

    def get_experiment_state(self):
        return "running"

    def save_and_park(self):
        self.parked = True

    def get_position(self):
        if self.position_raises:
            raise RuntimeError("gantry offline")
        return self.position

    def get_workspace_yaml(self):
        return self.workspace_yaml


class _PlainInstrument:
    """No experiment-lock support, like PHProbe."""

    def __init__(self, sila):
        self.sila = sila


@pytest.fixture
def fake_sila(monkeypatch):
    _FakeSilaClient.instances = []
    monkeypatch.setattr(client_module, "SilaClient", _FakeSilaClient)
    return _FakeSilaClient


def test_connect_with_explicit_host_exposes_instrument(fake_sila):
    with RxnBenchClient() as bench:
        bench.connect("ph", _PlainInstrument, host="192.168.1.10", port=50052)
        assert isinstance(bench.ph, _PlainInstrument)
        assert bench.ph.sila.host == "192.168.1.10"
        assert bench.ph.sila.port == 50052


def test_lock_goes_to_first_lock_capable_instrument_only(fake_sila):
    with RxnBenchClient() as bench:
        bench.connect("ph", _PlainInstrument, host="h", port=1)
        bench.connect("gantry", _LockCapableInstrument, host="h", port=2)
        bench.connect("gantry2", _LockCapableInstrument, host="h", port=3)
        assert bench.gantry.lock_acquired
        assert not bench.gantry2.lock_acquired
        assert bench._lock_holder is bench.gantry


def test_close_releases_lock_and_closes_every_channel(fake_sila):
    bench = RxnBenchClient()
    bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
    bench.connect("ph", _PlainInstrument, host="h", port=2)
    gantry = bench.gantry
    bench.close()
    assert gantry.lock_released
    assert all(c.closed for c in fake_sila.instances)
    assert bench._lock_holder is None


def test_close_survives_release_failure(fake_sila):
    """A dead server at teardown must not prevent channels from closing."""
    bench = RxnBenchClient()
    bench.connect("gantry", _LockCapableInstrument, host="h", port=1)

    def _boom():
        raise ConnectionError("server gone")
    bench.gantry.release_experiment_lock = _boom

    bench.close()  # must not raise
    assert all(c.closed for c in fake_sila.instances)


# auto-park on close (normal completion, manual stop, or script failure)

def test_normal_exit_parks_gantry(fake_sila):
    with RxnBenchClient() as bench:
        bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
    assert bench.gantry.parked
    assert bench.gantry.lock_released


def test_stop_requested_exit_parks_gantry_before_releasing_lock(fake_sila):
    """Mirrors a script propagating ExperimentStopped out of the `with` block."""
    order = []
    with pytest.raises(ExperimentStopped):
        with RxnBenchClient() as bench:
            bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
            bench.gantry.save_and_park = lambda: order.append("park")
            bench.gantry.release_experiment_lock = lambda: order.append("release")
            raise ExperimentStopped("stopped by user")
    assert order == ["park", "release"]


def test_unhandled_exception_exit_parks_gantry(fake_sila):
    """A mid-run failure (not just a user stop) must also leave the gantry parked."""
    with pytest.raises(ValueError):
        with RxnBenchClient() as bench:
            bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
            raise ValueError("probe fault")
    assert bench.gantry.parked


def test_park_failure_does_not_prevent_lock_release(fake_sila):
    """A dead motion server on the way out must not strand the experiment lock."""
    with pytest.raises(ExperimentStopped):
        with RxnBenchClient() as bench:
            bench.connect("gantry", _LockCapableInstrument, host="h", port=1)

            def _boom():
                raise ConnectionError("server gone")
            bench.gantry.save_and_park = _boom
            raise ExperimentStopped("stopped by user")
    assert bench.gantry.lock_released


def test_close_skips_instruments_without_save_and_park(fake_sila):
    """A connected PHProbe (no save_and_park) must not blow up close()."""
    with RxnBenchClient() as bench:
        bench.connect("ph", _PlainInstrument, host="h", port=1)


# start_experiment() - self-contained per-run results folder

def test_start_experiment_creates_timestamped_folder(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")

    folder = bench.start_experiment(script)

    assert folder.is_dir()
    assert folder.parent == tmp_path
    assert folder.name.startswith("my_tour_")
    assert bench.experiment_dir == folder


def test_start_experiment_points_log_output_at_the_folder(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")

    folder = bench.start_experiment(script)
    bench.log(ph=7.0)

    assert (folder / "results.csv").exists()


def test_start_experiment_copies_the_script_into_the_folder(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# original contents")

    folder = bench.start_experiment(script)

    assert (folder / "my_tour.py").read_text() == "# original contents"


def test_start_experiment_handles_missing_script_gracefully(bench, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    folder = bench.start_experiment(tmp_path / "does_not_exist.py")

    assert folder.is_dir()  # folder itself is still created
    assert not (folder / "does_not_exist.py").exists()
    assert "Could not copy script" in capsys.readouterr().out


def test_start_experiment_skips_workspace_snapshot_without_gantry(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")

    folder = bench.start_experiment(script)

    assert not (folder / "workspace.yaml").exists()


def test_start_experiment_saves_workspace_snapshot_when_gantry_attached(fake_sila, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")

    with RxnBenchClient() as bench:
        bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
        bench.gantry.workspace_yaml = "name: bench\nplates: []\n"

        folder = bench.start_experiment(script)

        assert (folder / "workspace.yaml").read_text() == "name: bench\nplates: []\n"


def test_start_experiment_writes_running_status_immediately(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")

    folder = bench.start_experiment(script)
    data = json.loads((folder / "experiment.json").read_text())

    assert data["script"] == "my_tour.py"
    assert data["status"] == "running"
    assert data["finished"] is None
    assert data["started"] is not None


def test_close_marks_experiment_completed_on_normal_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")
    folder = None

    with RxnBenchClient() as bench:
        folder = bench.start_experiment(script)

    data = json.loads((folder / "experiment.json").read_text())
    assert data["status"] == "completed"
    assert data["finished"] is not None


def test_exit_marks_experiment_failed_when_the_with_block_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")
    folder = None

    with pytest.raises(ValueError):
        with RxnBenchClient() as bench:
            folder = bench.start_experiment(script)
            raise ValueError("boom")

    data = json.loads((folder / "experiment.json").read_text())
    assert data["status"] == "failed"


def test_experiment_index_records_attached_device_names(fake_sila, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "my_tour.py"
    script.write_text("# a script")

    with RxnBenchClient() as bench:
        bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
        bench.connect("ph", _PlainInstrument, host="h", port=2)
        folder = bench.start_experiment(script)

    data = json.loads((folder / "experiment.json").read_text())
    assert data["devices"] == ["gantry", "ph"]


# bench.snapshot() and bench.workflow.step()'s automatic done/failed calls

class _FakeCamera:
    def __init__(self, raise_error: bool = False):
        self.saved_paths: list[str] = []
        self._raise = raise_error

    def save_snapshot(self, path):
        if self._raise:
            raise RuntimeError("camera offline")
        self.saved_paths.append(path)
        pathlib.Path(path).write_bytes(b"fake-jpeg-bytes")


def test_safe_filename_replaces_unsafe_characters():
    assert client_module._safe_filename("well:24-well4/A1") == "well_24-well4_A1"


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_snapshot_without_camera_is_a_noop(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.start_experiment(script)

    bench.snapshot("engaged")

    assert not (bench.experiment_dir / "images").exists()


def test_snapshot_without_experiment_dir_is_a_noop(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bench.camera = _FakeCamera()

    bench.snapshot("engaged")

    assert bench.camera.saved_paths == []


def test_snapshot_called_directly_outside_any_step(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.camera = _FakeCamera()
    bench.start_experiment(script)

    bench.snapshot("pre-dispense")

    rows = _read_jsonl(bench.experiment_dir / "images" / "images.jsonl")
    assert len(rows) == 1
    assert rows[0]["step_id"] is None  # no active bench.workflow.step()
    assert rows[0]["label"] == "pre-dispense"
    assert "pre-dispense" in rows[0]["image"]


def test_snapshot_called_multiple_times_inside_one_step(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.camera = _FakeCamera()
    bench.start_experiment(script)
    bench.set_workflow_output("wf.jsonl")

    with bench.workflow.step("well:A1"):
        bench.snapshot("engaged")
        bench.snapshot("disengaged")

    rows = _read_jsonl(bench.experiment_dir / "images" / "images.jsonl")
    # 2 ad hoc snapshots + 1 automatic "done" on successful step exit
    assert [r["label"] for r in rows] == ["engaged", "disengaged", "done"]
    assert all(r["step_id"] == "well:A1" for r in rows)


def test_workflow_step_saves_snapshot_on_failure(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.camera = _FakeCamera()
    bench.start_experiment(script)
    bench.set_workflow_output("wf.jsonl")

    with pytest.raises(RuntimeError, match="boom"):
        with bench.workflow.step("well:A1", idempotent=True):
            raise RuntimeError("boom")

    rows = _read_jsonl(bench.experiment_dir / "images" / "images.jsonl")
    assert rows[0]["label"] == "failed"
    assert rows[0]["step_id"] == "well:A1"
    # the real tracking outcome is unaffected by the snapshot
    assert not bench.workflow.is_done("well:A1")


def test_snapshot_logs_gantry_position(fake_sila, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")

    with RxnBenchClient() as bench:
        bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
        bench.gantry.position = (10.0, 20.0, 30.0)
        bench.camera = _FakeCamera()
        bench.start_experiment(script)

        bench.snapshot("engaged")

        rows = _read_jsonl(bench.experiment_dir / "images" / "images.jsonl")

    images = list((bench.experiment_dir / "images").glob("*.jpg"))
    assert len(rows) == 1
    assert rows[0]["position"] == {"x": 10.0, "y": 20.0, "z": 30.0}
    assert rows[0]["image"] == images[0].name


def test_snapshot_logs_null_position_without_gantry(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.camera = _FakeCamera()
    bench.start_experiment(script)

    bench.snapshot()

    rows = _read_jsonl(bench.experiment_dir / "images" / "images.jsonl")
    assert rows[0]["position"] is None


def test_snapshot_logs_null_position_when_gantry_read_fails(fake_sila, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")

    with RxnBenchClient() as bench:
        bench.connect("gantry", _LockCapableInstrument, host="h", port=1)
        bench.gantry.position_raises = True
        bench.camera = _FakeCamera()
        bench.start_experiment(script)

        bench.snapshot()

        rows = _read_jsonl(bench.experiment_dir / "images" / "images.jsonl")

    # the image is still saved and the row still written, just without a position
    assert len(list((bench.experiment_dir / "images").glob("*.jpg"))) == 1
    assert rows[0]["position"] is None


def test_snapshot_camera_error_does_not_raise(bench, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.camera = _FakeCamera(raise_error=True)
    bench.start_experiment(script)

    bench.snapshot()  # must not raise

    assert "Could not save snapshot" in capsys.readouterr().out


def test_workflow_step_camera_error_does_not_break_step_tracking(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.camera = _FakeCamera(raise_error=True)
    bench.start_experiment(script)
    bench.set_workflow_output("wf.jsonl")

    with bench.workflow.step("a"):
        pass  # step body succeeds even though the camera is broken

    assert bench.workflow.is_done("a")


# End-to-end: a real Gantry (not workflow.step()) auto-snapshotting via the
# real _attach() -> instrument._bench wiring, not just the instruments/
# unit tests exercising _snapshot() directly.

class _FakeGantrySilaFeature:
    def AcquireExperimentLock(self):
        return ("tok",)

    def ReleaseExperimentLock(self, **kw):
        pass

    def MoveToWell(self, **kw):
        pass


class _FakeGantrySila:
    def __init__(self):
        self.Gantry = _FakeGantrySilaFeature()

    def close(self):
        pass


def test_gantry_move_to_well_auto_snapshots_through_real_attach(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "s.py"
    script.write_text("# s")
    bench.camera = _FakeCamera()
    bench.start_experiment(script)

    bench._attach("gantry", Gantry, _FakeGantrySila())
    bench.gantry.move_to_well("plate1/A1")

    rows = _read_jsonl(bench.experiment_dir / "images" / "images.jsonl")
    assert rows[-1]["label"] == "move_to_well"


def test_workflow_remaining_and_is_done_pass_through_the_wrapper(bench, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bench.set_workflow_output("wf.jsonl")

    with bench.workflow.step("a"):
        pass

    assert list(bench.workflow.remaining(["a", "b"], key=lambda x: x)) == ["b"]
    assert bench.workflow.is_done("a")
