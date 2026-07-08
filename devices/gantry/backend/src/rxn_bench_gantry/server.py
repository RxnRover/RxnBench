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

    # get_axis_limits() is the single source of truth for the starting bounds -
    # Klipper's own configured travel range for real hardware, or the fixed
    # simulated bed for mock mode - instead of a second, separately maintained
    # set of numbers that can silently drift out of sync with it. This is only
    # the *initial* default: manual homing (confirm_x_min/max, confirm_y_min/max)
    # and its saved state always take precedence once calibrated, exactly as
    # before. Falls back to a conservative default if the query fails, so a
    # motion controller that's slow to come up doesn't take the whole SiLA
    # server down with it.
    try:
        limits = motion_client.get_axis_limits()
        x_min, x_max = limits["x"]
        y_min, y_max = limits["y"]
        z_min, z_max = limits["z"]
    except Exception as exc:
        log.warning("Could not query axis limits (%s) - using conservative defaults.", exc)
        x_min, x_max = 0.0, 350.0
        y_min, y_max = 0.0, 350.0
        z_min, z_max = 0.0, 340.0

    controller = GantryController(
        client=motion_client,
        x_min=x_min, x_max=x_max,
        y_min=y_min, y_max=y_max,
        z_min=z_min, z_max=z_max,
    )

    app.register(Gantry(controller=controller))
    yield app
