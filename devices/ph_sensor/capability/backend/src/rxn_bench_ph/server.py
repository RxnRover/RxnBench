"""
SiLA server app factory - pH Sensor device.

Start with: rxn-bench-ph

RXN_BENCH_MOCK=1 selects a simulated sensor, no hardware. Otherwise, the real
driver is loaded via the "rxn_bench.ph_drivers" entry-point group -
RXN_BENCH_PH_DRIVER picks which registered driver to use (default: "atlas_ezo",
provided by the rxn-bench-atlas-ezo-ph-driver package; its own environment
variables, e.g. RXN_BENCH_PH_TRANSPORT, configure that specific driver). This
capability package has no import-time dependency on any concrete driver -
a second pH probe vendor registers under the same entry-point group without
any change here.
"""
import importlib.metadata
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_ph.feature import PHSensor

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))
_DRIVER_NAME = os.environ.get("RXN_BENCH_PH_DRIVER", "atlas_ezo")
_DRIVER_GROUP = "rxn_bench.ph_drivers"


def _load_driver_factory(name: str):
    for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP):
        if ep.name == name:
            return ep.load()
    available = sorted(ep.name for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP))
    raise RuntimeError(
        f"No pH driver registered as {name!r} under the {_DRIVER_GROUP!r} entry-point "
        f"group; available: {available or '(none installed)'}"
    )


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup. Selects real or mock sensor."""
    app = Connector(config)

    if _MOCK:
        log.warning("MOCK MODE - using simulated pH sensor")
        from rxn_bench_ph.mock_ph_sensor import MockPHSensor
        sensor = MockPHSensor()
    else:
        try:
            build_sensor = _load_driver_factory(_DRIVER_NAME)
            sensor = build_sensor()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to initialise pH sensor: {exc}") from exc

    app.register(PHSensor(sensor=sensor))
    yield app
