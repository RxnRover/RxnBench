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

    # get_axis_limits() is the single source of truth for the starting *size*
    # of each axis - Klipper's own configured travel range for real hardware,
    # or the fixed simulated bed for mock mode - instead of a second,
    # separately maintained set of numbers that can silently drift out of
    # sync with it. Only the span (max - min) is taken from it, never
    # Klipper's raw absolute numbering: every workspace YAML, plate origin,
    # and HomingManager.confirm_x_min/y_min (which declares the operator's
    # confirmed corner *as* 0) assumes a 0-based frame throughout this app, so
    # min is always forced to 0 here regardless of what Klipper's own
    # position_min happens to be (which is sometimes negative, e.g. endstop
    # backoff clearance). This is only the *initial* default: manual homing
    # and its saved state always take precedence once calibrated, exactly as
    # before. Falls back to a conservative default if the query fails, so a
    # motion controller that's slow to come up doesn't take the whole SiLA
    # server down with it.
    try:
        limits = motion_client.get_axis_limits()
        x_min, x_max = 0.0, limits["x"][1] - limits["x"][0]
        y_min, y_max = 0.0, limits["y"][1] - limits["y"][0]
        z_min, z_max = 0.0, limits["z"][1] - limits["z"][0]
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
        z_clearance_padding_mm=machine.z_clearance_padding_mm,
    )

    app.register(Gantry(controller=controller))
    yield app
