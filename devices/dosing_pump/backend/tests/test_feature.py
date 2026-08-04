"""Tests for the DosingPump SiLA feature - the glue between DosingPumpProtocol and the wire.

No pytest-asyncio dependency is used (the project has none); coroutines are
driven directly with asyncio.run(), matching how a real event loop would call
them one step at a time.
"""
import asyncio

import pytest

from rxn_bench_dosing_pump.feature import DosingPump
from rxn_bench_dosing_pump.interfaces import (
    DosingPumpProtocol,
    SupportsCalibration,
    SupportsDiagnostics,
    SupportsDirectionInvert,
)


class _FakePump:
    def __init__(self):
        self.calls: list[tuple] = []
        self.volume = 2.5
        self.running = True
        self.paused = False
        self.inverted = False
        self.raise_on: str | None = None

    def _record(self, name, *args):
        self.calls.append((name, *args))
        if self.raise_on == name:
            raise RuntimeError(f"{name} failed")

    def read_volume_dispensed(self) -> float:
        return self.volume

    def is_dispensing(self) -> bool:
        return self.running

    def is_paused(self) -> bool:
        return self.paused

    def is_inverted(self) -> bool:
        return self.inverted

    def dispense_volume(self, volume): self._record("dispense_volume", volume)
    def dose_over_time(self, volume, minutes): self._record("dose_over_time", volume, minutes)
    def start_continuous_dispense(self, reverse): self._record("start_continuous_dispense", reverse)
    def set_flow_rate(self, rate, minutes): self._record("set_flow_rate", rate, minutes)
    def set_paused(self, paused): self._record("set_paused", paused)
    def set_inverted(self, inverted): self._record("set_inverted", inverted)
    def clear_total_volume(self): self._record("clear_total_volume")
    def calibrate(self, volume): self._record("calibrate", volume)
    def clear_calibration(self): self._record("clear_calibration")

    def stop_dispense(self) -> float:
        self._record("stop_dispense")
        return 7.25

    def total_volume_dispensed(self) -> float: return 100.0
    def absolute_total_volume(self) -> float: return 150.0
    def pump_voltage(self) -> float: return 13.86
    def max_flow_rate(self) -> float: return 58.5
    def calibration_status(self) -> int: return 3


async def _first(stream_fn):
    gen = stream_fn()
    try:
        return await gen.__anext__()
    finally:
        await gen.aclose()


# Observable properties

def test_volume_dispensed_stream_yields_pump_value():
    pump = _FakePump()
    pump.volume = 6.5
    feature = DosingPump(pump=pump)
    assert asyncio.run(_first(feature.volume_dispensed)) == 6.5


def test_dispensing_stream_yields_pump_state():
    pump = _FakePump()
    pump.running = False
    feature = DosingPump(pump=pump)
    assert asyncio.run(_first(feature.dispensing)) is False


# Unobservable properties

def test_unobservable_properties_forward():
    feature = DosingPump(pump=_FakePump())
    assert asyncio.run(feature.total_volume()) == 100.0
    assert asyncio.run(feature.absolute_total_volume()) == 150.0
    assert asyncio.run(feature.pump_voltage()) == 13.86
    assert asyncio.run(feature.max_flow_rate()) == 58.5
    assert asyncio.run(feature.paused()) is False
    assert asyncio.run(feature.inverted()) is False


# Commands

def test_dispense_forwards_volume():
    pump = _FakePump()
    asyncio.run(DosingPump(pump=pump).dispense(15.0))
    assert pump.calls == [("dispense_volume", 15.0)]


def test_dose_over_time_forwards_both_args():
    pump = _FakePump()
    asyncio.run(DosingPump(pump=pump).dose_over_time(85.0, 10.0))
    assert pump.calls == [("dose_over_time", 85.0, 10.0)]


def test_dispense_continuously_defaults_to_forward():
    pump = _FakePump()
    asyncio.run(DosingPump(pump=pump).dispense_continuously())
    assert pump.calls == [("start_continuous_dispense", False)]


def test_set_flow_rate_translates_zero_minutes_to_indefinite():
    pump = _FakePump()
    asyncio.run(DosingPump(pump=pump).set_flow_rate(25.0))
    assert pump.calls == [("set_flow_rate", 25.0, None)]


def test_set_flow_rate_passes_a_real_duration_through():
    pump = _FakePump()
    asyncio.run(DosingPump(pump=pump).set_flow_rate(25.0, 40.0))
    assert pump.calls == [("set_flow_rate", 25.0, 40.0)]


def test_stop_returns_volume_dispensed():
    pump = _FakePump()
    assert asyncio.run(DosingPump(pump=pump).stop()) == 7.25


def test_set_paused_and_set_inverted_forward():
    pump = _FakePump()
    feature = DosingPump(pump=pump)
    asyncio.run(feature.set_paused(True))
    asyncio.run(feature.set_inverted(True))
    assert pump.calls == [("set_paused", True), ("set_inverted", True)]


def test_calibration_commands_forward():
    pump = _FakePump()
    feature = DosingPump(pump=pump)
    asyncio.run(feature.calibrate(24.01))
    asyncio.run(feature.clear_calibration())
    assert pump.calls == [("calibrate", 24.01), ("clear_calibration",)]
    assert asyncio.run(feature.get_calibration_status()) == 3


def test_clear_total_volume_forwards():
    pump = _FakePump()
    asyncio.run(DosingPump(pump=pump).clear_total_volume())
    assert pump.calls == [("clear_total_volume",)]


def test_command_errors_propagate_to_the_caller():
    pump = _FakePump()
    pump.raise_on = "dispense_volume"
    with pytest.raises(RuntimeError, match="dispense_volume failed"):
        asyncio.run(DosingPump(pump=pump).dispense(15.0))


# Reuse: a second pump model implementing only the core protocol

class _CoreOnlyPump:
    """A pump with no calibration, no direction flip, no voltage sensing.

    Stands in for a different model reusing this feature/proto/widget - the
    point of splitting DosingPumpProtocol from the capability protocols.
    """

    def __init__(self):
        self.calls: list[tuple] = []

    def read_volume_dispensed(self) -> float: return 1.0
    def is_dispensing(self) -> bool: return False
    def is_paused(self) -> bool: return False
    def max_flow_rate(self) -> float: return 20.0
    def total_volume_dispensed(self) -> float: return 5.0
    def absolute_total_volume(self) -> float: return 5.0
    def stop_dispense(self) -> float: return 1.0

    def dispense_volume(self, volume): self.calls.append(("dispense_volume", volume))
    def dose_over_time(self, volume, minutes): self.calls.append(("dose_over_time", volume, minutes))
    def start_continuous_dispense(self, reverse): self.calls.append(("continuous", reverse))
    def set_flow_rate(self, rate, minutes): self.calls.append(("set_flow_rate", rate, minutes))
    def set_paused(self, paused): self.calls.append(("set_paused", paused))
    def clear_total_volume(self): self.calls.append(("clear_total_volume",))


def test_core_only_pump_satisfies_the_core_protocol_but_not_the_optional_ones():
    pump = _CoreOnlyPump()
    assert isinstance(pump, DosingPumpProtocol)
    assert not isinstance(pump, SupportsCalibration)
    assert not isinstance(pump, SupportsDirectionInvert)
    assert not isinstance(pump, SupportsDiagnostics)


def test_core_only_pump_serves_every_dispensing_command():
    pump = _CoreOnlyPump()
    feature = DosingPump(pump=pump)
    asyncio.run(feature.dispense(5.0))
    asyncio.run(feature.dose_over_time(5.0, 2.0))
    asyncio.run(feature.dispense_continuously())
    asyncio.run(feature.set_flow_rate(3.0))
    asyncio.run(feature.set_paused(True))
    asyncio.run(feature.clear_total_volume())
    assert asyncio.run(feature.stop()) == 1.0
    assert asyncio.run(feature.total_volume()) == 5.0
    assert asyncio.run(feature.max_flow_rate()) == 20.0
    assert [c[0] for c in pump.calls] == [
        "dispense_volume", "dose_over_time", "continuous",
        "set_flow_rate", "set_paused", "clear_total_volume",
    ]


@pytest.mark.parametrize("call, missing", [
    (lambda f: f.calibrate(1.0), "calibration"),
    (lambda f: f.clear_calibration(), "calibration"),
    (lambda f: f.get_calibration_status(), "calibration"),
    (lambda f: f.set_inverted(True), "direction flip"),
    (lambda f: f.inverted(), "direction flip"),
    (lambda f: f.pump_voltage(), "supply voltage"),
])
def test_unsupported_capabilities_fail_with_a_message_naming_what_is_missing(call, missing):
    feature = DosingPump(pump=_CoreOnlyPump())
    with pytest.raises(NotImplementedError, match=missing):
        asyncio.run(call(feature))
