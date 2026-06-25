"""
Entry point and app factory for the Automated Chem Bench SiLA server.

Wires up hardware drivers and registers SiLA features. Add new features
here as devices come online.

Author: John Brittain
Date: Jun 17 2026
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from chem_bench.machine_config import MachineConfig
from chem_bench.io.gantry.gantry_controller import GantryController
from chem_bench.io.gantry.moonraker_client import MoonrakerClient
from chem_bench.io.gantry.moonraker_discovery import find_moonraker
from chem_bench.features.gantry import Gantry
from chem_bench.features.ph_sensor import PHSensor

log = logging.getLogger(__name__)

# Set CHEM_BENCH_MOCK=1 to run with simulated hardware (no physical devices required).
_MOCK_MODE = bool(os.environ.get("CHEM_BENCH_MOCK"))


async def create_app(config):
    app = Connector(config)
    machine = MachineConfig.load()

    if _MOCK_MODE:
        log.warning("MOCK MODE — using simulated hardware, no devices connected")
        from chem_bench.io.gantry.mock_moonraker import MockMoonrakerClient
        from chem_bench.io.ph.mock_ph_sensor import MockPHSensor
        motion_client = MockMoonrakerClient()
        ph_sensor = MockPHSensor()
    else:
        log.info("Searching for Moonraker...")
        host = await find_moonraker(timeout=10.0)
        if host:
            log.info("Moonraker found at %s", host)
        else:
            host = machine.moonraker_fallback_host
            log.warning("Moonraker not discovered — falling back to %s", host)
        motion_client = MoonrakerClient(host)

        try:
            from smbus2 import SMBus
            from chem_bench.io.ph.atlas_ph_sensor import AtlasPHSensor
            ph_sensor = AtlasPHSensor(SMBus(1))
            log.info("Atlas pH sensor initialised on I2C bus 1")
        except ImportError:
            log.warning(
                "smbus2 not installed — pH sensor unavailable. "
                "Install with: pip install chem-bench[rpi]"
            )
            ph_sensor = None
        except Exception as exc:
            log.warning("Failed to initialise pH sensor (%s) — skipping.", exc)
            ph_sensor = None

    gantry_controller = GantryController(
        client=motion_client,
        clearance_z=machine.clearance_z,
        x_min=machine.x_min,
        x_max=machine.x_max,
        y_min=machine.y_min,
        y_max=machine.y_max,
        z_min=machine.z_min,
        z_max=machine.z_max,
        sensor_registry={"ph": ph_sensor} if ph_sensor else {},
    )

    app.register(Gantry(controller=gantry_controller))

    if ph_sensor is not None:
        app.register(PHSensor(sensor=ph_sensor))

    yield app
