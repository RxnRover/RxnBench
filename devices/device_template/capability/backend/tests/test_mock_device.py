"""
Starter tests for the device template.

TODO: rename imports and add tests that exercise your real Protocol methods,
      feature behaviour, and any config loading. Use the gantry tests in
      devices/gantry/backend/tests/ as examples of what to cover.
"""
from rxn_bench_template.interfaces import MyDeviceProtocol
from rxn_bench_template.mock_device import MockMyDevice


def test_mock_satisfies_protocol():
    assert isinstance(MockMyDevice(), MyDeviceProtocol)


def test_mock_read_returns_float():
    device = MockMyDevice()
    result = device.read()
    assert isinstance(result, float)


def test_mock_action_does_not_raise():
    device = MockMyDevice()
    device.do_action(1.0)
