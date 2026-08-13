"""Tests for the DosingPump instrument wrapper's auto-snapshot behavior."""
import pytest

import rxn_bench_client.instruments.pump as pump_module
from rxn_bench_client.instruments.pump import DosingPump

from .conftest import FakeSubscription


class _FakeValueProperty:
    """Serves a scripted sequence of values, one per subscribe()."""

    def __init__(self, values):
        self._values = list(values)

    def subscribe(self):
        value = self._values.pop(0) if len(self._values) > 1 else self._values[0]
        return FakeSubscription(value)


class _FakeDosingPumpFeature:
    def __init__(self, dispensing_sequence, volume=5.0):
        self.Dispensing = _FakeValueProperty(dispensing_sequence)
        self.VolumeDispensed = _FakeValueProperty([volume])
        self.dispense_calls: list[float] = []

    def Dispense(self, Volume):
        self.dispense_calls.append(Volume)


class _FakeDosingPumpSila:
    def __init__(self, dispensing_sequence):
        self.DosingPump = _FakeDosingPumpFeature(dispensing_sequence)


class _FakeBench:
    def __init__(self):
        self.snapshots: list[str] = []

    def snapshot(self, label):
        self.snapshots.append(label)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(pump_module.time, "sleep", lambda *_a, **_k: None)


def _pump(dispensing_sequence):
    return DosingPump(_FakeDosingPumpSila(dispensing_sequence))


def test_dispense_and_wait_auto_snapshots_on_completion():
    pump = _pump([True, False])  # dispensing, then done
    pump._bench = _FakeBench()
    pump.dispense_and_wait(5.0)
    assert pump._bench.snapshots == ["dispense_and_wait"]


def test_dispense_does_not_auto_snapshot():
    """dispense() returns immediately - the pump hasn't finished (or even
    started) delivering anything yet, so there's nothing worth a picture of."""
    pump = _pump([False])
    pump._bench = _FakeBench()
    pump.dispense(5.0)
    assert pump._bench.snapshots == []


def test_dispense_and_wait_does_not_snapshot_without_a_bench():
    _pump([False]).dispense_and_wait(5.0)  # must not raise
