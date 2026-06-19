"""
Entry point and app factory for the Automated Chem Bench SiLA server.

Wires up hardware drivers and registers SiLA features. Add new features
here as devices come online.

Author: John Brittain
Date: Jun 17 2026
"""
import logging

from unitelabs.cdk.connector import Connector

from chem_bench.io.motion_platform.motion_platform_controller import MotionPlatformController
from chem_bench.io.motion_platform.moonraker_discovery import find_moonraker
from chem_bench.features.motion_platform import MotionPlatform

log = logging.getLogger(__name__)

# Fallback Moonraker host if discovery fails, static IP
MOONRAKER_FALLBACK = "192.168.10.2"


async def create_app(config):
    app = Connector(config)

    log.info("Searching for Moonraker...")
    host = await find_moonraker(timeout=10.0)
    if host:
        log.info("Moonraker found at %s", host)
    else:
        host = MOONRAKER_FALLBACK
        log.warning("Moonraker not discovered - falling back to %s", host)

    motion_controller = MotionPlatformController(moonraker_host=host)
    app.register(MotionPlatform(controller=motion_controller))

    # Register more features here as devices come online, e.g.:
    # app.register(PHSensor(sensor=AtlasPHSensor()))

    yield app
