"""Tests for MockEZOUart, the EZO-pH UART protocol emulator.

Mirrors test_mock_i2c.py: checks the emulator answers the ASCII commands a
physical EZO circuit would over serial (CR-terminated data lines framed by
``*OK``/``*ER``) behind the write/read_until port interface.
"""
from rxn_bench_atlas_ezo_ph_driver.mock_uart import MockEZOUart


def _drain(port) -> list[bytes]:
    """Pop every queued reply line from the port."""
    lines = []
    while True:
        line = port.read_until(b"\r")
        if not line:
            return lines
        lines.append(line)


def test_read_command_returns_value_then_ok():
    port = MockEZOUart(ph=7.2)
    port.write(b"R\r")
    assert _drain(port) == [b"7.200\r", b"*OK\r"]
    assert port.commands == ["R"]


def test_read_until_empty_when_nothing_queued():
    port = MockEZOUart()
    assert port.read_until(b"\r") == b""


def test_reset_input_buffer_discards_queued_lines():
    port = MockEZOUart()
    port.write(b"R\r")
    port.reset_input_buffer()
    assert port.read_until(b"\r") == b""


def test_command_strips_cr_terminator():
    port = MockEZOUart()
    port.write(b"Status\r")
    assert port.commands == ["Status"]


def test_calibrate_ack_only_returns_ok():
    port = MockEZOUart()
    port.write(b"Cal,mid,7.0\r")
    assert _drain(port) == [b"*OK\r"]
    assert "mid" in port.calibration_points


def test_slope_query_returns_data_then_ok():
    port = MockEZOUart(acid_slope=99.7, base_slope=100.3)
    port.write(b"Slope,?\r")
    assert _drain(port) == [b"?Slope,99.7,100.3\r", b"*OK\r"]


def test_continuous_off_toggles_state():
    port = MockEZOUart()
    assert port.continuous is True
    port.write(b"C,0\r")
    assert _drain(port) == [b"*OK\r"]
    assert port.continuous is False


def test_unknown_command_returns_error():
    port = MockEZOUart()
    port.write(b"Bogus\r")
    assert _drain(port) == [b"*ER\r"]
