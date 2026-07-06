"""
SiLA server app factory - pH Sensor device.

Start with: rxn-bench-ph
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_ph.feature import PHSensor

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup. Selects real or mock sensor."""
    app = Connector(config)

    if _MOCK:
        log.warning("MOCK MODE - using simulated pH sensor")
        from rxn_bench_ph.mock_ph_sensor import MockPHSensor
        sensor = MockPHSensor()
    else:
        try:
            from smbus2 import SMBus
            from rxn_bench_ph.atlas_ph_sensor import AtlasPHSensor
            from rxn_bench_ph.i2c_bus import SMBusI2C
            # SMBusI2C adapts smbus2 to the raw write/read byte-stream
            # interface the EZO driver expects - SMBus alone has no such API.
            sensor = AtlasPHSensor(SMBusI2C(SMBus(1)))
            log.info("Atlas pH sensor initialised on I2C bus 1")
        except ImportError:
            raise RuntimeError(
                "smbus2 is required to run the pH sensor server. "
                "Install with: pip install rxn-bench-ph[rpi]"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialise pH sensor: {exc}") from exc

    app.register(PHSensor(sensor=sensor))
    yield app
