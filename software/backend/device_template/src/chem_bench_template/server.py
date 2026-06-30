"""
SiLA server app factory - wires hardware to the SiLA feature.

Called by the CDK when the server starts. Yields the configured Connector.
Hardware initialisation goes here; the feature itself stays hardware-agnostic.

TODO: update imports to use your renamed classes.
      Add any hardware initialisation your device needs (serial port, I2C bus,
      network connection, etc.) inside the `else` branch below.
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from chem_bench_template.feature import MyDevice  # TODO: rename

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("CHEM_BENCH_MOCK"))


async def create_app(config):
    app = Connector(config)

    if _MOCK:
        log.warning("MOCK MODE - using simulated device")
        from chem_bench_template.mock_device import MockMyDevice  # TODO: rename
        device = MockMyDevice()
    else:
        try:
            # TODO: replace this block with your real hardware initialisation.
            # Examples:
            #   Serial:  import serial; hw = serial.Serial("/dev/ttyUSB0", 9600)
            #   I2C:     from smbus2 import SMBus; hw = SMBus(1)
            #   Network: hw = MyDeviceClient("192.168.1.10", port=5000)
            # Then wrap it:
            #   from chem_bench_template.my_driver import MyDriver
            #   device = MyDriver(hw)
            raise NotImplementedError(
                "Real hardware initialisation not yet implemented. "
                "Run with CHEM_BENCH_MOCK=1 for development."
            )
        except NotImplementedError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialise device: {exc}\n"
                "Check hardware connections and run with CHEM_BENCH_MOCK=1 to bypass."
            ) from exc

    app.register(MyDevice(device=device))  # TODO: rename MyDevice
    yield app
