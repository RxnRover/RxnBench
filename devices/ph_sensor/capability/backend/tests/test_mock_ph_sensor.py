"""Tests for the in-memory mock pH sensor used in RXN_BENCH_MOCK=1 mode."""
from rxn_bench_ph.interfaces import PHSensorProtocol
from rxn_bench_ph.mock_ph_sensor import MockPHSensor


def test_satisfies_protocol():
    assert isinstance(MockPHSensor(), PHSensorProtocol)


def test_read_returns_reading_in_valid_ph_range():
    sensor = MockPHSensor()
    reading = sensor.read()
    assert reading.unit == "pH"
    assert reading.sensor_id == "mock_ph"
    assert 1.0 <= reading.value <= 14.0


def test_calibrate_does_not_raise():
    sensor = MockPHSensor()
    sensor.calibrate("mid", 7.0)
    sensor.calibrate("clear", 0.0)


def test_slope_returns_nominal_tuple():
    sensor = MockPHSensor()
    assert sensor.slope() == (99.7, 100.3)


def test_temperature_defaults_to_25_and_roundtrips():
    sensor = MockPHSensor()
    assert sensor.get_temperature() == 25.0
    sensor.set_temperature(18.5)
    assert sensor.get_temperature() == 18.5
