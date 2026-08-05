"""Tests for the Atlas Scientific EZO-PMP UART driver.

Happy-path protocol handling runs against MockEZOPumpUart (the real emulator),
so the whole AtlasScientificEZOPumpUart command stack executes end-to-end.
Error, timeout, and *DONE-framing paths use a small scripted/silent fake port,
with a fast fake clock so the timeout branch doesn't actually wait.
"""
from collections import deque

import pytest

import rxn_bench_dosing_pump.atlas_scientific_uart_driver as uart_mod
from rxn_bench_dosing_pump.atlas_scientific_uart_driver import AtlasScientificEZOPumpUart
from rxn_bench_dosing_pump.mock_uart import MockEZOPumpUart


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


@pytest.fixture
def clock():
    class _Clock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    return _Clock()


def _driver(**kwargs):
    port = MockEZOPumpUart(**kwargs)
    return AtlasScientificEZOPumpUart(port), port


def _scripted(lines):
    return AtlasScientificEZOPumpUart(_ScriptedPort(lines), disable_continuous=False)


# Startup

def test_init_disables_continuous_mode():
    _, port = _driver()
    assert "C,0" in port.commands
    assert port.continuous_reporting == "0"


# Command encoding

def test_dispense_volume_formats_without_trailing_zeros():
    driver, port = _driver()
    driver.dispense_volume(15.0)
    assert "D,15" in port.commands


def test_dispense_volume_keeps_decimals_and_sign():
    driver, port = _driver()
    driver.dispense_volume(-40.5)
    assert "D,-40.5" in port.commands


def test_dispense_continuously_forward_and_reverse():
    driver, port = _driver()
    driver.dispense_continuously()
    driver.dispense_continuously(reverse=True)
    assert "D,*" in port.commands
    assert "D,-*" in port.commands


def test_dose_over_time_sends_volume_and_minutes():
    driver, port = _driver()
    driver.dose_over_time(85, 10)
    assert "D,85,10" in port.commands


def test_set_constant_flow_rate_with_duration():
    driver, port = _driver()
    driver.set_constant_flow_rate(25, 40)
    assert "DC,25,40" in port.commands


def test_set_constant_flow_rate_indefinite_uses_asterisk():
    driver, port = _driver()
    driver.set_constant_flow_rate(25)
    assert "DC,25,*" in port.commands


# Response parsing

def test_read_volume_dispensed_parses_float(clock):
    driver, port = _driver(clock=clock)
    driver.dose_over_time(10, 10)
    clock.now += 180.0
    assert driver.read_volume_dispensed() == 3.0


def test_get_max_flow_rate_parses_maxrate():
    driver, _ = _driver(max_flow_rate=58.5)
    assert driver.get_max_flow_rate() == 58.5


def test_get_dispense_status_returns_volume_and_running(clock):
    driver, port = _driver(clock=clock)
    driver.dose_over_time(10, 10)
    assert driver.get_dispense_status() == (10.0, True)
    clock.now += 6000.0
    _, running = driver.get_dispense_status()
    assert running is False


def test_get_dispense_status_handles_asterisk_volume_while_continuous():
    driver, _ = _driver()
    driver.dispense_continuously()
    volume, running = driver.get_dispense_status()
    assert volume == 0.0
    assert running is True


def test_get_pump_voltage_parses_float():
    driver, _ = _driver(pump_voltage=13.86)
    assert driver.get_pump_voltage() == 13.86


def test_total_volume_commands_parse(clock):
    driver, port = _driver(clock=clock)
    driver.dose_over_time(-10, 10)
    clock.now += 6000.0
    driver.read_volume_dispensed()
    assert driver.get_total_volume() == -10.0
    assert driver.get_absolute_total_volume() == 10.0


def test_clear_total_volume_resets(clock):
    driver, port = _driver(clock=clock)
    driver.dose_over_time(5, 1)
    clock.now += 600.0
    driver.read_volume_dispensed()
    driver.clear_total_volume()
    assert driver.get_total_volume() == 0.0


def test_calibration_status_roundtrip():
    driver, _ = _driver()
    assert driver.get_calibration_status() == 0
    driver.calibrate(24.01)
    assert driver.get_calibration_status() == 1
    driver.clear_calibration()
    assert driver.get_calibration_status() == 0


def test_pause_and_invert_status_parse_bools():
    driver, _ = _driver()
    assert driver.get_pause_status() is False
    driver.pause()
    assert driver.get_pause_status() is True
    assert driver.get_invert_status() is False
    driver.invert()
    assert driver.get_invert_status() is True


def test_get_info_returns_data_line():
    driver, _ = _driver()
    assert driver.get_info() == "?i,PMP,1.1"


# Circuit housekeeping

def test_led_roundtrip():
    driver, port = _driver()
    assert driver.get_led() is True
    driver.set_led(False)
    assert driver.get_led() is False
    assert "L,0" in port.commands


def test_protocol_lock_roundtrip():
    driver, port = _driver()
    assert driver.get_protocol_lock() is False
    driver.set_protocol_lock(True)
    assert driver.get_protocol_lock() is True
    assert "Plock,1" in port.commands


def test_find_sends_command_and_disables_continuous_mode():
    driver, port = _driver()
    driver.find()
    assert "Find" in port.commands
    assert port.finding is True
    assert port.continuous_reporting == "0"


def test_find_does_not_corrupt_the_next_read():
    driver, port = _driver(pump_voltage=13.86)
    driver.find()
    assert driver.get_pump_voltage() == 13.86


def test_sleep_puts_the_circuit_to_sleep():
    driver, port = _driver()
    driver.sleep()
    assert "Sleep" in port.commands
    assert port.asleep is True


# These two deliberately run on the real clock: the fast_clock fixture would
# also expire sleep()'s own read. They each wait out one real read timeout
# (~1.3s), which is the behaviour under test.

def test_command_while_asleep_only_gets_wa_and_raises():
    # Faithful to hardware: the waking byte is consumed, not executed, so the
    # circuit answers *WA and the in-flight command never runs.
    driver, port = _driver()
    driver.sleep()
    with pytest.raises(IOError):
        driver.get_pump_voltage()


def test_wake_absorbs_the_swallowed_command():
    driver, port = _driver()
    driver.sleep()
    driver.wake()                      # must not raise, despite only getting *WA
    assert port.asleep is False
    assert driver.get_pump_voltage() == 13.86


# *DONE framing

def test_stop_parses_done_volume(clock):
    driver, port = _driver(clock=clock)
    driver.dose_over_time(10, 10)
    clock.now += 300.0
    assert driver.stop() == 5.0


def test_stop_reads_done_as_its_reply_with_no_ok():
    driver = _scripted([b"*DONE,10.15\r"])
    assert driver.stop() == 10.15


def test_unsolicited_done_before_a_data_line_does_not_hijack_the_reply():
    # A dispense completing at the same moment as a TV,? query: the *DONE must
    # be skipped, not returned as the total volume.
    driver = _scripted([b"*DONE,10.00\r", b"?TV,434.50\r", b"*OK\r"])
    assert driver.get_total_volume() == 434.50


def test_unsolicited_done_after_a_data_line_does_not_truncate_the_reply():
    driver = _scripted([b"?TV,434.50\r", b"*DONE,10.00\r", b"*OK\r"])
    assert driver.get_total_volume() == 434.50


def test_unsolicited_done_is_recorded_for_later_inspection():
    driver = _scripted([b"*DONE,10.00\r", b"?TV,434.50\r", b"*OK\r"])
    driver.get_total_volume()
    assert driver.last_completed_volume == 10.00


def test_malformed_done_volume_is_ignored_not_fatal():
    driver = _scripted([b"*DONE,oops\r", b"?TV,1.00\r", b"*OK\r"])
    assert driver.get_total_volume() == 1.0
    assert driver.last_completed_volume is None


# Errors

def test_error_response_raises_valueerror():
    driver = _scripted([b"*ER\r"])
    with pytest.raises(ValueError, match=r"\*ER"):
        driver.read_volume_dispensed()


def test_minvol_rejection_names_the_minimum():
    driver = _scripted([b"*MINVOL\r", b"*ER\r"])
    with pytest.raises(ValueError, match="0.5ml minimum"):
        driver.dispense_volume(0.2)


def test_toofast_rejection_names_the_rate():
    driver = _scripted([b"*TOOFAST\r", b"*ER\r"])
    with pytest.raises(ValueError, match="calibrated maximum"):
        driver.set_constant_flow_rate(500, 1)


def test_timeout_with_no_response_raises_ioerror(fast_clock):
    driver = _scripted([])
    with pytest.raises(IOError):
        driver.read_volume_dispensed()


def test_async_status_lines_are_ignored():
    driver = _scripted([b"*RS\r", b"?PV,13.86\r", b"*OK\r"])
    assert driver.get_pump_voltage() == 13.86


def test_malformed_response_with_missing_fields_raises():
    driver = _scripted([b"?PV\r", b"*OK\r"])
    with pytest.raises(ValueError, match="Malformed"):
        driver.get_pump_voltage()


def test_stale_line_does_not_corrupt_the_next_read(clock):
    # A queued reply from an earlier command must be drained before the next
    # command's reply is read.
    driver, port = _driver(clock=clock)
    port.write(b"i\r")                 # queue a reply nobody reads
    assert driver.get_pump_voltage() == 13.86
