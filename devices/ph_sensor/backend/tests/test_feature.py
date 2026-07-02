"""Tests for the PHSensor SiLA feature - the glue between PHSensorProtocol and the wire.

No pytest-asyncio dependency is used (the project has none); coroutines are
driven directly with asyncio.run(), matching how a real event loop would call
them one step at a time.
"""
import asyncio

import pytest

from rxn_bench_ph.base_sensor import SensorReading
from rxn_bench_ph.enums import CalibrationPoint
from rxn_bench_ph.feature import PHSensor


class _FakeSensor:
    def __init__(self, value: float = 7.0, slope=(99.7, 100.3)):
        self._value = value
        self._slope = slope
        self.calibrate_calls: list[tuple[str, float]] = []
        self.raise_on_calibrate: Exception | None = None

    def read(self) -> SensorReading:
        return SensorReading(value=self._value, unit="pH", sensor_id="fake")

    def calibrate(self, point: str, value: float) -> None:
        self.calibrate_calls.append((point, value))
        if self.raise_on_calibrate:
            raise self.raise_on_calibrate

    def slope(self) -> tuple[float, float]:
        return self._slope


async def _first_ph_value(feature: PHSensor) -> float:
    gen = feature.ph()
    try:
        return await gen.__anext__()
    finally:
        await gen.aclose()


def test_ph_property_yields_sensor_reading():
    sensor = _FakeSensor(value=6.5)
    feature = PHSensor(sensor=sensor)
    assert asyncio.run(_first_ph_value(feature)) == 6.5


def test_probe_slope_returns_str_of_sensor_slope():
    sensor = _FakeSensor(slope=(99.7, 100.3))
    feature = PHSensor(sensor=sensor)
    assert asyncio.run(feature.probe_slope()) == str((99.7, 100.3))


def test_calibrate_forwards_to_sensor():
    sensor = _FakeSensor()
    feature = PHSensor(sensor=sensor)
    asyncio.run(feature.calibrate(CalibrationPoint.MID, 7.0))
    assert sensor.calibrate_calls == [(CalibrationPoint.MID, 7.0)]


def test_calibrate_reraises_sensor_errors():
    sensor = _FakeSensor()
    sensor.raise_on_calibrate = RuntimeError("probe not responding")
    feature = PHSensor(sensor=sensor)
    with pytest.raises(RuntimeError, match="probe not responding"):
        asyncio.run(feature.calibrate(CalibrationPoint.LOW, 4.0))
