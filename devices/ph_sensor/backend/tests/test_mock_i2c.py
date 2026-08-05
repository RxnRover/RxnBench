"""End-to-end tests of the real pH driver stack over MockI2CBus.

Unlike test_atlas_scientific_driver.py (which pins wire-protocol parsing with
preprogrammed responses), these run AtlasScientificEZO and AtlasPHSensor
against the EZO protocol emulator - the same code path a real sensor takes,
minus the physical bus.
"""
import pytest

import rxn_bench_ph.base_driver as base_driver
from rxn_bench_ph.atlas_ph_sensor import AtlasPHSensor
from rxn_bench_ph.mock_i2c import MockI2CBus


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(base_driver.time, "sleep", lambda *_args, **_kwargs: None)


@pytest.fixture
def bus():
    return MockI2CBus(ph=7.2)


@pytest.fixture
def sensor(bus):
    return AtlasPHSensor(bus)


def test_read_returns_configured_ph(sensor):
    reading = sensor.read()
    assert reading.value == pytest.approx(7.2, abs=1e-3)
    assert reading.unit == "pH"


def test_read_tracks_changing_ph(sensor, bus):
    bus.ph = 4.01
    assert sensor.read().value == pytest.approx(4.01, abs=1e-3)


def test_three_point_calibration_flow(sensor):
    """The full calibrate sequence a chemist would run: mid, low, high."""
    sensor.calibrate("mid", 7.0)
    sensor.calibrate("low", 4.0)
    sensor.calibrate("high", 10.0)
    assert sensor.calibration_status() == 3
    acid, base = sensor.slope()
    assert acid == pytest.approx(99.7)
    assert base == pytest.approx(100.3)


def test_clear_calibration_resets_points(sensor):
    sensor.calibrate("mid", 7.0)
    sensor.calibrate("clear", 0.0)
    assert sensor.calibration_status() == 0


def test_unknown_calibration_point_raises_before_touching_bus(sensor, bus):
    with pytest.raises(ValueError, match="calibration point"):
        sensor.calibrate("sideways", 7.0)
    assert not any(c.startswith("Cal,sideways") for c in bus.commands)


def test_temperature_compensation_round_trip(sensor):
    sensor.set_temperature(23.5)
    assert sensor.get_temperature() == pytest.approx(23.5)


def test_status_reports_voltage(sensor):
    status = sensor.status()
    assert status["restart_reason"] == "P"
    assert status["voltage"] == pytest.approx(3.83)


def test_led_round_trip(sensor):
    sensor.set_led(False)
    assert sensor.get_led() is False
    sensor.set_led(True)
    assert sensor.get_led() is True


def test_syntax_error_response_raises_value_error(sensor, bus):
    """An unknown command gets the EZO syntax-error status byte -> ValueError."""
    bus._response = b"\x02"
    with pytest.raises(ValueError, match="Syntax error"):
        sensor._driver._read_response(delay_ms=0)
