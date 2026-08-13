"""Tests for the Atlas Scientific EZO-pH UART driver.

Happy-path protocol handling runs against MockEZOUart (the real emulator), so
the whole AtlasScientificEZOUart command stack executes end-to-end. Error and
timeout paths use a small scripted/silent fake port, with a fast fake clock so
the timeout branch doesn't actually wait.
"""
from collections import deque

import pytest

import rxn_bench_atlas_ezo_ph_driver.atlas_scientific_uart_driver as uart_mod
from rxn_bench_atlas_ezo_ph_driver.atlas_scientific_uart_driver import AtlasScientificEZOUart
from rxn_bench_atlas_ezo_ph_driver.mock_uart import MockEZOUart


class _ScriptedPort:
    """Returns preloaded CR-terminated lines; reset_input_buffer is a no-op so the script survives."""

    def __init__(self, lines=()):
        self._queue = deque(lines)
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def read_until(self, expected: bytes = b"\r") -> bytes:
        return self._queue.popleft() if self._queue else b""

    def reset_input_buffer(self) -> None:
        pass


@pytest.fixture
def fast_clock(monkeypatch):
    """Make time.monotonic jump forward each call so timeout loops exit immediately."""
    state = {"t": 0.0}

    def _monotonic():
        state["t"] += 10.0
        return state["t"]

    monkeypatch.setattr(uart_mod.time, "monotonic", _monotonic)


def _driver(**kwargs) -> tuple[AtlasScientificEZOUart, MockEZOUart]:
    port = MockEZOUart(**kwargs)
    return AtlasScientificEZOUart(port), port


def test_init_disables_continuous_mode():
    driver, port = _driver()
    assert "C,0" in port.commands
    assert port.continuous is False


def test_read_ph_sends_r_and_parses_float():
    driver, port = _driver(ph=7.0)
    assert driver.read_ph() == 7.0
    assert "R" in port.commands


def test_read_ph_uses_updated_mock_value():
    driver, port = _driver(ph=4.321)
    assert driver.read_ph() == 4.321


def test_calibrate_mid_sends_command_and_consumes_ok():
    driver, port = _driver()
    driver.calibrate_mid(7.0)
    assert "Cal,mid,7.0" in port.commands
    assert "mid" in port.calibration_points


def test_get_slope_parses_two_floats():
    driver, port = _driver(acid_slope=99.7, base_slope=100.3)
    assert driver.get_slope() == (99.7, 100.3)


def test_get_calibration_status_parses_int():
    driver, port = _driver()
    driver.calibrate_mid(7.0)
    driver.calibrate_low(4.0)
    assert driver.get_calibration_status() == 2


def test_get_led_roundtrip():
    driver, port = _driver()
    driver.set_led(False)
    assert driver.get_led() is False


def test_send_only_command_does_not_corrupt_next_read():
    # Find sends a command but reads no reply; its *OK must not be mistaken
    # for the following read's response.
    driver, port = _driver(ph=6.5)
    driver.find()
    assert driver.read_ph() == 6.5


def test_error_response_raises_valueerror():
    port = _ScriptedPort([b"*ER\r"])
    driver = AtlasScientificEZOUart(port, disable_continuous=False)
    with pytest.raises(ValueError):
        driver.read_ph()


def test_data_line_before_ok_is_returned():
    port = _ScriptedPort([b"7.004\r", b"*OK\r"])
    driver = AtlasScientificEZOUart(port, disable_continuous=False)
    assert driver.read_ph() == 7.004


def test_timeout_with_no_response_raises_ioerror(fast_clock):
    port = _ScriptedPort([])  # nothing to return
    driver = AtlasScientificEZOUart(port, disable_continuous=False)
    with pytest.raises(IOError):
        driver.read_ph()


def test_async_status_lines_are_ignored():
    # *RS (reset) then the real data then *OK - the status line must be skipped.
    port = _ScriptedPort([b"*RS\r", b"7.010\r", b"*OK\r"])
    driver = AtlasScientificEZOUart(port, disable_continuous=False)
    assert driver.read_ph() == 7.01
