"""Tests for the low-level Atlas Scientific EZO-pH I2C command/response parsing.

Uses a fake I2C bus double instead of real hardware - only the wire-protocol
parsing (status byte handling, comma-separated response decoding) is under
test here, not actual I2C timing.
"""
import pytest

import rxn_bench_atlas_ezo_ph_driver.base_driver as base_driver
from rxn_bench_atlas_ezo_ph_driver.atlas_scientific_driver import AtlasScientificEZO


class _FakeI2CBus:
    """Records the last command written and returns a preprogrammed response."""

    def __init__(self, response: bytes = b""):
        self.response = response
        self.last_write: bytes | None = None

    def write(self, address: int, data: bytes) -> None:
        self.last_write = data

    def read(self, address: int, num_bytes: int) -> bytes:
        return self.response


def _ok_response(payload: str) -> bytes:
    """Build a status-OK response: status byte 1 + ascii payload, null-padded to 31 bytes."""
    body = b"\x01" + payload.encode("ascii")
    return body.ljust(31, b"\x00")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Driver calls time.sleep(delay_ms/1000) between write and read; skip it in tests."""
    monkeypatch.setattr(base_driver.time, "sleep", lambda *_args, **_kwargs: None)


def _driver(response: bytes = b"") -> tuple[AtlasScientificEZO, _FakeI2CBus]:
    bus = _FakeI2CBus(response)
    return AtlasScientificEZO(bus, address=0x63), bus


def test_read_ph_sends_r_command_and_parses_float():
    driver, bus = _driver(_ok_response("7.00"))
    assert driver.read_ph() == 7.00
    assert bus.last_write == b"R"


def test_parse_response_empty_raises_ioerror():
    driver, _ = _driver(b"")
    with pytest.raises(IOError):
        driver.read_ph()


def test_parse_response_not_ready_raises_ioerror():
    driver, _ = _driver(b"\xfe" + b"\x00" * 30)  # 254 = _STATUS_NOT_READY
    with pytest.raises(IOError):
        driver.read_ph()


def test_parse_response_syntax_error_raises_valueerror():
    driver, _ = _driver(b"\x02" + b"\x00" * 30)  # 2 = _STATUS_SYNTAX_ERR
    with pytest.raises(ValueError):
        driver.read_ph()


def test_parse_response_no_data_raises_ioerror():
    driver, _ = _driver(b"\xff" + b"\x00" * 30)  # 255 = _STATUS_NO_DATA
    with pytest.raises(IOError):
        driver.read_ph()


def test_parse_response_unexpected_code_raises_ioerror():
    driver, _ = _driver(b"\x63" + b"\x00" * 30)  # arbitrary unknown code
    with pytest.raises(IOError):
        driver.read_ph()


def test_get_slope_parses_two_floats():
    driver, _ = _driver(_ok_response("?Slope,99.7,100.3"))
    assert driver.get_slope() == (99.7, 100.3)


def test_get_calibration_status_parses_int():
    driver, _ = _driver(_ok_response("?Cal,3"))
    assert driver.get_calibration_status() == 3


def test_get_temperature_compensation_parses_float():
    driver, _ = _driver(_ok_response("?T,25.0"))
    assert driver.get_temperature_compensation() == 25.0


def test_get_led_true():
    driver, _ = _driver(_ok_response("?L,1"))
    assert driver.get_led() is True


def test_get_led_false():
    driver, _ = _driver(_ok_response("?L,0"))
    assert driver.get_led() is False


def test_set_led_sends_correct_command():
    driver, bus = _driver(_ok_response("?L,1"))
    driver.set_led(True)
    assert bus.last_write == b"L,1"


def test_calibrate_mid_sends_correct_command():
    driver, bus = _driver(_ok_response(""))
    driver.calibrate_mid(7.0)
    assert bus.last_write == b"Cal,mid,7.0"
