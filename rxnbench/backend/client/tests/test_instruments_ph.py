"""Tests for the PHProbe instrument wrapper, including its stability logic.

A fake SiLA client stands in for the live server, serving a scripted
sequence of pH values one per subscribe().
"""
import pytest

import rxn_bench_client.instruments.ph as ph_module
from rxn_bench_client.instruments.ph import PHProbe, _StabilityMonitor, _regression_slope

from .conftest import FakeSubscription


class _FakePhProperty:
    """Serves a scripted sequence of pH values, one per subscribe()."""

    def __init__(self, values):
        self._values = list(values)

    def subscribe(self):
        value = self._values.pop(0) if len(self._values) > 1 else self._values[0]
        return FakeSubscription(value)


class _FakePHSensorFeature:
    def __init__(self, values):
        self.Ph = _FakePhProperty(values)
        self.calibrate_calls: list[tuple] = []

    def Calibrate(self, **kw):
        self.calibrate_calls.append(kw)


class _FakePHSila:
    def __init__(self, values):
        self.PHSensor = _FakePHSensorFeature(values)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(ph_module.time, "sleep", lambda *_a, **_k: None)


def _probe(values):
    return PHProbe(_FakePHSila(values))


def test_read_returns_single_value():
    assert _probe([7.21]).read() == pytest.approx(7.21)


def test_read_avg_averages_n_readings():
    probe = _probe([7.0, 7.2, 7.4])
    assert probe.read_avg(n=3, interval=0) == pytest.approx(7.2)


# --- Endpoint-detection stability logic ------------------------------------
#
# The window/slope/range/consecutive-count math lives in _StabilityMonitor, which
# is fed (elapsed_seconds, pH) samples directly, so these tests exercise it
# without a clock. The read_stable() I/O loop is covered separately below.


def _monitor(**overrides):
    """Default-config monitor: 5-reading window, 5 s settle, 0.002 pH/s drift,
    0.02 pH range, 3 consecutive windows - overridable per test."""
    cfg = dict(window=5, min_settle=5.0, max_drift=0.002, max_range=0.02, stable_checks=3)
    cfg.update(overrides)
    return _StabilityMonitor(**cfg)


def test_stability_accepts_flat_signal():
    # A dead-flat 1 Hz signal settles after the window fills, the settle time
    # passes, and three consecutive windows pass - not before.
    mon = _monitor()
    results = [mon.update(float(t), 7.00) for t in range(8)]
    assert not any(results[:7])            # window+settle+3-in-a-row gate
    assert results[7] is True
    assert mon.mean() == pytest.approx(7.00)


def test_stability_rejects_slow_drift_within_range():
    # +0.004 pH/s creep: over a 4 s window the spread is only 0.016 pH (inside
    # max_range) but the slope exceeds max_drift, so it must never be accepted.
    mon = _monitor()
    stream = [(float(t), 7.00 + 0.004 * t) for t in range(21)]
    assert not any(mon.update(t, v) for t, v in stream)
    assert mon.ptp() <= 0.02               # range criterion is satisfied...
    assert abs(mon.slope()) > 0.002        # ...but the drift criterion is not


def test_stability_rejects_noisy_signal_with_large_range():
    # Alternating 7.00/7.05: the drift averages to ~0 but the 0.05 pH swing
    # blows past max_range, so the range criterion holds it out.
    mon = _monitor()
    stream = [(float(t), 7.00 if t % 2 == 0 else 7.05) for t in range(21)]
    assert not any(mon.update(t, v) for t, v in stream)
    assert abs(mon.slope()) <= 0.002       # drift criterion is satisfied...
    assert mon.ptp() > 0.02                # ...but the range criterion is not


def test_stability_settles_after_initial_drift():
    # A steep ramp that then plateaus at 7.20: not stable while drifting, but
    # once the window is entirely on the plateau it settles on the mean.
    mon = _monitor()
    stream = [(float(t), 7.00 + 0.05 * t) for t in range(6)]        # drift, t=0..5
    stream += [(float(t), 7.20) for t in range(6, 20)]             # plateau
    results = [mon.update(t, v) for t, v in stream]
    assert not any(results[:6])            # unstable through the ramp
    assert results[-1] is True             # eventually settles
    assert mon.mean() == pytest.approx(7.20)


def test_stability_requires_three_consecutive_windows():
    # Two passing windows are not enough; the third consecutive one settles it.
    mon = _monitor()
    for t in range(5):                     # fill window (t=4 is still < min_settle)
        assert mon.update(float(t), 7.00) is False
    assert mon.update(5.0, 7.00) is False   # 1st passing window
    assert mon.update(6.0, 7.00) is False   # 2nd passing window - still short
    assert mon.update(7.0, 7.00) is True    # 3rd consecutive -> settled


def test_stability_streak_resets_on_failing_window():
    # A single out-of-range excursion resets the consecutive count, so the
    # required streak has to be rebuilt from scratch.
    mon = _monitor(window=2, min_settle=0.0)
    assert mon.update(0.0, 7.00) is False   # window not full yet
    assert mon.update(1.0, 7.00) is False   # pass 1
    assert mon.update(2.0, 7.00) is False   # pass 2
    assert mon.update(3.0, 7.30) is False   # excursion fails -> reset (else pass 3)
    assert mon.update(4.0, 7.30) is False   # pass 1 again
    assert mon.update(5.0, 7.30) is False   # pass 2
    assert mon.update(6.0, 7.30) is True    # pass 3 -> settled


def test_stability_ignores_nan_and_resets_streak():
    # A NaN reading is dropped from the window and breaks the stable streak.
    mon = _monitor()
    for t in range(7):
        mon.update(float(t), 7.00)          # streak building; count is 2 by t=6
    assert mon.update(7.0, float("nan")) is False   # dropped + streak reset
    assert mon.update(8.0, 7.00) is False           # count 1 (proves the reset)
    assert mon.update(9.0, 7.00) is False           # count 2
    assert mon.update(10.0, 7.00) is True           # count 3 -> settled


def test_stability_rejects_bad_config():
    with pytest.raises(ValueError, match="window must be at least 2"):
        _monitor(window=1)
    with pytest.raises(ValueError, match="stable_checks must be at least 1"):
        _monitor(stable_checks=0)


def test_regression_slope_handles_degenerate_inputs():
    assert _regression_slope([0.0, 1.0, 2.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert _regression_slope([5.0], [7.0]) == 0.0            # too few points
    assert _regression_slope([2.0, 2.0, 2.0], [7.0, 7.1, 7.2]) == 0.0  # equal times


# --- read_stable() I/O loop ------------------------------------------------


class _StepClock:
    """time.monotonic() stand-in: 0 for the first call (read_stable's start
    marker), then 0, 1, 2, ... nominal seconds - one per reading at 1 Hz."""

    def __init__(self, step: float = 1.0) -> None:
        self._step = step
        self._n = 0

    def __call__(self) -> float:
        n = self._n
        self._n += 1
        return max(0, n - 1) * self._step


def test_read_stable_returns_window_mean_when_settled(monkeypatch):
    monkeypatch.setattr(ph_module.time, "monotonic", _StepClock())
    assert _probe([7.00]).read_stable() == pytest.approx(7.00)


def test_read_stable_times_out_and_returns_best_effort_reading(monkeypatch, capsys):
    monkeypatch.setattr(ph_module.time, "monotonic", _StepClock())
    # A steep, never-settling ramp; the timeout fires before stability. Never
    # raises - returns the latest valid reading instead of crashing the caller.
    probe = _probe([7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0])
    result = probe.read_stable(timeout=5.0)
    assert result == pytest.approx(9.5)   # best/latest reading kept
    assert "WARNING" in capsys.readouterr().out


def test_read_stable_rejects_bad_config():
    with pytest.raises(ValueError, match="window must be at least 2"):
        _probe([7.0]).read_stable(window=1)


def test_read_stable_uses_fresh_state_each_call(monkeypatch):
    # Each call builds its own monitor, so a second measurement isn't polluted
    # by the first.
    probe = _probe([7.00])
    monkeypatch.setattr(ph_module.time, "monotonic", _StepClock())
    assert probe.read_stable() == pytest.approx(7.00)
    monkeypatch.setattr(ph_module.time, "monotonic", _StepClock())
    assert probe.read_stable() == pytest.approx(7.00)


def test_wait_for_above_returns_first_crossing():
    probe = _probe([6.5, 6.8, 7.2])
    assert probe.wait_for(above=7.0, interval=0) == pytest.approx(7.2)


def test_wait_for_requires_a_threshold():
    with pytest.raises(ValueError, match="above= or below="):
        _probe([7.0]).wait_for()


def test_wait_for_timeout_raises():
    probe = _probe([7.0])
    with pytest.raises(TimeoutError, match="did not reach"):
        probe.wait_for(below=5.0, timeout=0.0, interval=0)


# Auto-snapshot: calibrate() asks the owning bench for a picture

class _FakeBench:
    def __init__(self):
        self.snapshots: list[str] = []

    def snapshot(self, label):
        self.snapshots.append(label)


def test_calibrate_auto_snapshots_when_attached_to_a_bench():
    probe = _probe([7.0])
    probe._bench = _FakeBench()
    probe.calibrate("mid", 7.0)
    assert probe._bench.snapshots == ["calibrate_mid"]


def test_reads_do_not_auto_snapshot():
    """read()/read_avg()/read_stable() poll every ~1s - snapshotting them
    would flood the log."""
    probe = _probe([7.0, 7.0, 7.0])
    probe._bench = _FakeBench()
    probe.read()
    probe.read_avg(n=2, interval=0)
    assert probe._bench.snapshots == []


def test_calibrate_does_not_snapshot_without_a_bench():
    _probe([7.0]).calibrate("clear", 0.0)  # must not raise
