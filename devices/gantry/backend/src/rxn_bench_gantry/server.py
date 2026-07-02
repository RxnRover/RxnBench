"""
SiLA server app factory - Gantry device.

Start with: rxn-bench-gantry
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_gantry.machine_config import MachineConfig
from rxn_bench_gantry.controller import GantryController
from rxn_bench_gantry.moonraker_client import MoonrakerClient
from rxn_bench_gantry.moonraker_discovery import find_moonraker
from rxn_bench_gantry.feature import Gantry

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup.

    Args:
        config: CDK configuration object injected by the framework.
    """
    app = Connector(config)
    machine = MachineConfig.load()

    if _MOCK:
        log.warning("MOCK MODE - using simulated motion hardware")
        from rxn_bench_gantry.mock_moonraker import MockMoonrakerClient
        motion_client = MockMoonrakerClient()
    else:
        log.info("Searching for Moonraker...")
        host = await find_moonraker(timeout=10.0)
        if host:
            log.info("Moonraker found at %s", host)
        else:
            host = machine.moonraker_fallback_host
            log.warning("Moonraker not discovered - falling back to %s", host)
        motion_client = MoonrakerClient(host)

    if _MOCK:
        controller = GantryController(
            client=motion_client,
            clearance_z=machine.clearance_z,
            x_min=-500.0,
            x_max=1000.0,
            y_min=-500.0,
            y_max=1000.0,
            z_min=-500.0,
            z_max=1000.0,
        )
    else:
        controller = GantryController(
            client=motion_client,
            clearance_z=machine.clearance_z,
            x_min=machine.x_min,
            x_max=machine.x_max,
            y_min=machine.y_min,
            y_max=machine.y_max,
            z_min=machine.z_min,
            z_max=machine.z_max,
        )

    app.register(Gantry(controller=controller))
    yield app
