"""Tests for AtlasPHSensor's calibration dispatch and status parsing.

Runs against a fake I2C bus so the real AtlasScientificEZO driver executes
normally underneath - only AtlasPHSensor's own logic (point dispatch, status
dict shape) is what these tests care about.
"""
import pytest

import rxn_bench_atlas_ezo_ph_driver.base_driver as base_driver
from rxn_bench_atlas_ezo_ph_driver.atlas_ph_sensor import AtlasPHSensor


class _FakeI2CBus:
    def __init__(self, response: bytes = b""):
        self.response = response
        self.last_write: bytes | None = None

    def write(self, address: int, data: bytes) -> None:
        self.last_write = data

    def read(self, address: int, num_bytes: int) -> bytes:
        return self.response


def _ok_response(payload: str) -> bytes:
    body = b"\x01" + payload.encode("ascii")
    return body.ljust(31, b"\x00")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(base_driver.time, "sleep", lambda *_args, **_kwargs: None)


def _sensor(response: bytes = b"") -> tuple[AtlasPHSensor, _FakeI2CBus]:
    bus = _FakeI2CBus(response)
    return AtlasPHSensor(bus, sensor_id="atlas_ph_test"), bus


def test_read_returns_reading_with_sensor_id():
    sensor, _ = _sensor(_ok_response("7.00"))
    reading = sensor.read()
    assert reading.value == 7.00
    assert reading.sensor_id == "atlas_ph_test"


@pytest.mark.parametrize(
    "point,value,expected_command",
    [
        ("mid", 7.0, b"Cal,mid,7.0"),
        ("low", 4.0, b"Cal,low,4.0"),
        ("high", 10.0, b"Cal,high,10.0"),
        ("clear", 0.0, b"Cal,clear"),
    ],
)
def test_calibrate_dispatches_to_correct_command(point, value, expected_command):
    sensor, bus = _sensor(_ok_response(""))
    sensor.calibrate(point, value)
    assert bus.last_write == expected_command


def test_calibrate_unknown_point_raises_valueerror_without_touching_bus():
    sensor, bus = _sensor(_ok_response(""))
    with pytest.raises(ValueError):
        sensor.calibrate("bogus", 1.0)
    assert bus.last_write is None


def test_slope_returns_driver_tuple():
    sensor, _ = _sensor(_ok_response("?Slope,99.7,100.3"))
    assert sensor.slope() == (99.7, 100.3)


def test_status_parses_restart_reason_and_voltage():
    sensor, _ = _sensor(_ok_response("?Status,P,3.3"))
    status = sensor.status()
    assert status == {"restart_reason": "P", "voltage": 3.3}


def test_status_handles_short_response():
    sensor, _ = _sensor(_ok_response("?Status"))
    status = sensor.status()
    assert status == {"restart_reason": None, "voltage": None}


def test_sensor_accepts_injected_uart_driver():
    """The driver= keyword lets the sensor run over UART instead of I2C."""
    from rxn_bench_atlas_ezo_ph_driver.atlas_scientific_uart_driver import AtlasScientificEZOUart
    from rxn_bench_atlas_ezo_ph_driver.mock_uart import MockEZOUart

    sensor = AtlasPHSensor(driver=AtlasScientificEZOUart(MockEZOUart(ph=7.2)), sensor_id="uart_ph")
    reading = sensor.read()
    assert reading.value == 7.2
    assert reading.sensor_id == "uart_ph"


def test_sensor_requires_bus_or_driver():
    with pytest.raises(ValueError):
        AtlasPHSensor()
