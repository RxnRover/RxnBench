"""Tests for RxnBenchClient - session management, at_well, pause/stop, CSV logging.

No servers or hardware: instruments are lightweight fakes, SilaClient is
monkeypatched out, and time.sleep is disabled. Mirrors the fake-based style of
the gantry/pH backend suites.
"""
import csv

import pytest

import rxn_bench_client.client as client_module
from rxn_bench_client.client import ExperimentStopped, RxnBenchClient


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


def test_log_with_explicit_columns_writes_header_up_front(bench, tmp_path):
    out = tmp_path / "results.csv"
    bench.set_log_output(out, columns=["ph"])
    assert out.read_text().strip() == "timestamp,ph"
    bench.log(ph=6.5, ignored="dropped")  # extrasaction="ignore"
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["ph"] == "6.5" and "ignored" not in rows[0]


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

    def acquire_experiment_lock(self):
        self.lock_acquired = True

    def release_experiment_lock(self):
        self.lock_released = True

    def get_experiment_state(self):
        return "running"


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
