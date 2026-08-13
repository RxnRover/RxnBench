"""Tests for the EZO-PMP UART protocol emulator itself.

These assert the emulator's own behaviour (wire syntax, dispense simulation)
so the driver tests can trust it as a stand-in for hardware.
"""
import pytest

from rxn_bench_atlas_ezo_pmp_driver.mock_uart import MockEZOPumpUart

_CR = b"\r"


def _exchange(port: MockEZOPumpUart, cmd: str) -> list[str]:
    """Send a command and drain every queued reply line."""
    port.write(cmd.encode("ascii") + _CR)
    lines = []
    while True:
        line = port.read_until(_CR)
        if not line:
            return lines
        lines.append(line.rstrip(_CR).decode("ascii"))


@pytest.fixture
def clock():
    """Mutable fake clock: `clock.now += 60` advances one minute."""
    class _Clock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    return _Clock()


def test_unknown_command_returns_error():
    assert _exchange(MockEZOPumpUart(), "NOPE") == ["*ER"]


def test_default_continuous_reporting_is_every_second():
    assert _exchange(MockEZOPumpUart(), "C,?") == ["?C,*", "*OK"]


def test_continuous_reporting_can_be_disabled():
    port = MockEZOPumpUart()
    assert _exchange(port, "C,0") == ["*OK"]
    assert port.continuous_reporting == "0"


def test_volume_below_minimum_is_rejected():
    assert _exchange(MockEZOPumpUart(), "D,0.2") == ["*MINVOL", "*ER"]


def test_flow_rate_above_max_is_rejected():
    port = MockEZOPumpUart(max_flow_rate=58.5)
    assert _exchange(port, "DC,100,10") == ["*TOOFAST", "*ER"]


def test_dose_over_time_implying_too_fast_a_rate_is_rejected():
    port = MockEZOPumpUart(max_flow_rate=58.5)
    # 100ml in 1 minute = 100 ml/min, above the maximum.
    assert _exchange(port, "D,100,1") == ["*TOOFAST", "*ER"]


def test_dispense_status_reports_running_then_stopped(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,10")
    assert _exchange(port, "D,?") == ["?D,10.00,1", "*OK"]
    clock.now += 600.0                       # far longer than the dose needs
    # The completion also emits its unsolicited *DONE here.
    assert _exchange(port, "D,?") == ["*DONE,10.00", "?D,10.00,0", "*OK"]


def test_continuous_dispense_reports_asterisk_volume(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,*")
    assert _exchange(port, "D,?") == ["?D,*,1", "*OK"]


def test_dose_over_time_progresses_proportionally(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,10,10")               # 10ml over 10 min = 1 ml/min
    clock.now += 180.0                       # 3 minutes
    assert _exchange(port, "R") == ["3.00", "*OK"]


def test_dose_over_time_caps_at_target(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,10,10")
    clock.now += 6000.0
    assert _exchange(port, "R") == ["*DONE,10.00", "10.00", "*OK"]


def test_paused_dispense_stops_accumulating(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,10,10")
    clock.now += 120.0                       # 2 min -> 2ml
    _exchange(port, "P")                     # pause
    clock.now += 300.0                       # 5 min of paused time
    assert _exchange(port, "R") == ["2.00", "*OK"]
    assert _exchange(port, "P,?") == ["?P,1", "*OK"]


def test_stop_reports_volume_and_banks_totals(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,10,10")
    clock.now += 300.0                       # 5 min -> 5ml
    assert _exchange(port, "X") == ["*DONE,5.00"]
    assert _exchange(port, "TV,?") == ["?TV,5.00", "*OK"]


def test_natural_completion_emits_unsolicited_done_before_next_reply(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,10,10")
    clock.now += 6000.0
    # The *DONE lands ahead of the queried value on purpose.
    assert _exchange(port, "TV,?") == ["*DONE,10.00", "?TV,10.00", "*OK"]


def test_stop_does_not_replay_done_on_the_next_command(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,10,10")
    clock.now += 300.0
    _exchange(port, "X")
    assert _exchange(port, "PV,?") == ["?PV,13.86", "*OK"]


def test_reverse_dispense_subtracts_from_total_but_not_absolute(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,-10,10")
    clock.now += 6000.0
    _exchange(port, "R")                     # let the emulator settle the dose
    assert _exchange(port, "TV,?") == ["?TV,-10.00", "*OK"]
    assert _exchange(port, "ATV,?") == ["?ATV,10.00", "*OK"]


def test_clear_resets_totals(clock):
    port = MockEZOPumpUart(clock=clock)
    _exchange(port, "D,5")
    clock.now += 600.0
    _exchange(port, "R")
    _exchange(port, "Clear")
    assert _exchange(port, "TV,?") == ["?TV,0.00", "*OK"]


def test_invert_toggles_and_reports():
    port = MockEZOPumpUart()
    assert _exchange(port, "Invert,?") == ["?Invert,0", "*OK"]
    _exchange(port, "Invert")
    assert _exchange(port, "Invert,?") == ["?Invert,1", "*OK"]


def test_calibration_status_roundtrip():
    port = MockEZOPumpUart()
    assert _exchange(port, "Cal,?") == ["?Cal,0", "*OK"]
    _exchange(port, "Cal,24.01")
    assert _exchange(port, "Cal,?") == ["?Cal,1", "*OK"]
    _exchange(port, "Cal,clear")
    assert _exchange(port, "Cal,?") == ["?Cal,0", "*OK"]


def test_max_flow_rate_and_info():
    port = MockEZOPumpUart(max_flow_rate=58.5)
    assert _exchange(port, "DC,?") == ["?MAXRATE,58.5", "*OK"]
    assert _exchange(port, "i") == ["?i,PMP,1.1", "*OK"]


def test_led_and_plock_roundtrip():
    port = MockEZOPumpUart()
    assert _exchange(port, "L,?") == ["?L,1", "*OK"]
    _exchange(port, "L,0")
    assert _exchange(port, "L,?") == ["?L,0", "*OK"]
    assert _exchange(port, "Plock,?") == ["?Plock,0", "*OK"]
    _exchange(port, "Plock,1")
    assert _exchange(port, "Plock,?") == ["?Plock,1", "*OK"]


def test_sleep_then_any_command_returns_only_wa():
    port = MockEZOPumpUart()
    assert _exchange(port, "Sleep") == ["*OK", "*SL"]
    assert port.asleep is True
    # The waking command is consumed, not executed.
    assert _exchange(port, "PV,?") == ["*WA"]
    assert port.asleep is False
    assert _exchange(port, "PV,?") == ["?PV,13.86", "*OK"]


def test_find_disables_continuous_mode_and_ends_on_next_command():
    port = MockEZOPumpUart()
    assert _exchange(port, "Find") == ["*OK"]
    assert port.finding is True
    assert port.continuous_reporting == "0"
    _exchange(port, "i")
    assert port.finding is False


def test_reset_input_buffer_discards_queued_replies():
    port = MockEZOPumpUart()
    port.write(b"i" + _CR)
    port.reset_input_buffer()
    assert port.read_until(_CR) == b""
