"""
SiLA server app factory - pH Sensor device.

Start with: chem-bench-ph
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from chem_bench_ph.feature import PHSensor

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("CHEM_BENCH_MOCK"))


async def create_app(config):
    app = Connector(config)

    if _MOCK:
        log.warning("MOCK MODE - using simulated pH sensor")
        from chem_bench_ph.mock_ph_sensor import MockPHSensor
        sensor = MockPHSensor()
    else:
        try:
            from smbus2 import SMBus
            from chem_bench_ph.atlas_ph_sensor import AtlasPHSensor
            sensor = AtlasPHSensor(SMBus(1))
            log.info("Atlas pH sensor initialised on I2C bus 1")
        except ImportError:
            raise RuntimeError(
                "smbus2 is required to run the pH sensor server. "
                "Install with: pip install chem-bench-ph[rpi]"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialise pH sensor: {exc}") from exc

    app.register(PHSensor(sensor=sensor))
    yield app
