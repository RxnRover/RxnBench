"""Tests for AtlasDosingPump / MockDosingPump - the Protocol-facing layer.

Covers the adapter's real job: turning the pump's two toggle commands into
idempotent setters.
"""
import pytest

from rxn_bench_dosing_pump.interfaces import DosingPumpProtocol
from rxn_bench_dosing_pump.mock_device import MockDosingPump


@pytest.fixture
def clock():
    class _Clock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    return _Clock()


def test_mock_satisfies_protocol():
    assert isinstance(MockDosingPump(), DosingPumpProtocol)


def test_dispense_then_read_volume(clock):
    pump = MockDosingPump(clock=clock)
    pump.dose_over_time(10, 10)
    clock.now += 300.0
    assert pump.read_volume_dispensed() == 5.0


def test_is_dispensing_tracks_the_dose(clock):
    pump = MockDosingPump(clock=clock)
    assert pump.is_dispensing() is False
    pump.dose_over_time(10, 10)
    assert pump.is_dispensing() is True
    clock.now += 6000.0
    assert pump.is_dispensing() is False


def test_stop_returns_volume_dispensed(clock):
    pump = MockDosingPump(clock=clock)
    pump.dose_over_time(10, 10)
    clock.now += 300.0
    assert pump.stop_dispense() == 5.0
    assert pump.is_dispensing() is False


def test_set_paused_is_idempotent(clock):
    pump = MockDosingPump(clock=clock)
    pump.dose_over_time(10, 10)
    pump.set_paused(True)
    assert pump.is_paused() is True
    pump.set_paused(True)                       # must not toggle back
    assert pump.is_paused() is True
    pump.set_paused(False)
    assert pump.is_paused() is False


def test_set_paused_sends_no_command_when_already_in_state(clock):
    pump = MockDosingPump(clock=clock)
    pump.dose_over_time(10, 10)
    pump.set_paused(False)                      # already unpaused
    assert "P" not in pump.port.commands


def test_set_inverted_is_idempotent():
    pump = MockDosingPump()
    pump.set_inverted(True)
    assert pump.is_inverted() is True
    pump.set_inverted(True)
    assert pump.is_inverted() is True
    pump.set_inverted(False)
    assert pump.is_inverted() is False


def test_paused_dispense_makes_no_progress(clock):
    pump = MockDosingPump(clock=clock)
    pump.dose_over_time(10, 10)
    clock.now += 120.0
    pump.set_paused(True)
    clock.now += 600.0
    assert pump.read_volume_dispensed() == 2.0


def test_totals_and_clear(clock):
    pump = MockDosingPump(clock=clock)
    pump.dispense_volume(5)
    clock.now += 600.0
    pump.read_volume_dispensed()
    assert pump.total_volume_dispensed() == 5.0
    assert pump.absolute_total_volume() == 5.0
    pump.clear_total_volume()
    assert pump.total_volume_dispensed() == 0.0


def test_reverse_dispense_signs(clock):
    pump = MockDosingPump(clock=clock)
    pump.dispense_volume(-5)
    clock.now += 600.0
    pump.read_volume_dispensed()
    assert pump.total_volume_dispensed() == -5.0
    assert pump.absolute_total_volume() == 5.0


def test_calibration_roundtrip():
    pump = MockDosingPump()
    assert pump.calibration_status() == 0
    pump.calibrate(24.01)
    assert pump.calibration_status() == 1
    pump.clear_calibration()
    assert pump.calibration_status() == 0


def test_diagnostics():
    pump = MockDosingPump(pump_voltage=13.86, max_flow_rate=58.5)
    assert pump.pump_voltage() == 13.86
    assert pump.max_flow_rate() == 58.5
    assert pump.status() == {"restart_reason": "P", "voltage": 5.038}
    assert pump.info() == "?i,PMP,1.1"


def test_housekeeping_led_find_sleep_wake():
    pump = MockDosingPump()
    assert pump.get_led() is True
    pump.set_led(False)
    assert pump.get_led() is False

    pump.find()
    assert pump.port.finding is True

    pump.sleep()
    assert pump.port.asleep is True
    pump.wake()
    assert pump.port.asleep is False
    assert pump.pump_voltage() == 13.86    # usable again after waking


def test_below_minimum_volume_raises():
    pump = MockDosingPump()
    with pytest.raises(ValueError, match="0.5ml minimum"):
        pump.dispense_volume(0.2)


def test_flow_rate_above_maximum_raises():
    pump = MockDosingPump(max_flow_rate=58.5)
    with pytest.raises(ValueError, match="calibrated maximum"):
        pump.set_flow_rate(100, 10)
