"""
SiLA server app factory - pH Sensor device.

Start with: rxn-bench-ph

Transport is chosen at startup by environment variables, mirroring RXN_BENCH_MOCK:
    RXN_BENCH_MOCK=1              - simulated sensor, no hardware
    RXN_BENCH_PH_TRANSPORT=i2c   - Atlas EZO-pH over I2C (default)
    RXN_BENCH_PH_TRANSPORT=uart  - Atlas EZO-pH over UART/serial
        RXN_BENCH_PH_SERIAL_PORT=/dev/serial0   (default)
        RXN_BENCH_PH_BAUD=9600                  (default; EZO UART default)
    RXN_BENCH_PH_I2C_BUS=1       - I2C bus number (default)

Set these in the systemd unit (e.g. `sudo systemctl edit rxn-bench-ph` ->
[Service] Environment=RXN_BENCH_PH_TRANSPORT=uart).
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_ph.feature import PHSensor

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))
_TRANSPORT = os.environ.get("RXN_BENCH_PH_TRANSPORT", "i2c").lower()


def _make_i2c_sensor():
    """Build an AtlasPHSensor talking to the EZO-pH over I2C."""
    try:
        from smbus2 import SMBus
        from rxn_bench_ph.atlas_ph_sensor import AtlasPHSensor
        from rxn_bench_ph.i2c_bus import SMBusI2C
    except ImportError:
        raise RuntimeError(
            "smbus2 is required to run the pH sensor server over I2C. "
            "Install with: pip install rxn-bench-ph[rpi]"
        )
    bus_num = int(os.environ.get("RXN_BENCH_PH_I2C_BUS", "1"))
    # SMBusI2C adapts smbus2 to the raw write/read byte-stream interface the
    # EZO driver expects - SMBus alone has no such API.
    sensor = AtlasPHSensor(SMBusI2C(SMBus(bus_num)))
    log.info("Atlas pH sensor initialised on I2C bus %d", bus_num)
    return sensor


def _make_uart_sensor():
    """Build an AtlasPHSensor talking to the EZO-pH over UART/serial."""
    try:
        import serial
        from rxn_bench_ph.atlas_ph_sensor import AtlasPHSensor
        from rxn_bench_ph.atlas_scientific_uart_driver import (
            AtlasScientificEZOUart,
            DEFAULT_BAUD_RATE,
        )
    except ImportError:
        raise RuntimeError(
            "pyserial is required to run the pH sensor server over UART. "
            "Install with: pip install rxn-bench-ph[rpi]"
        )
    port_name = os.environ.get("RXN_BENCH_PH_SERIAL_PORT", "/dev/serial0")
    baud = int(os.environ.get("RXN_BENCH_PH_BAUD", str(DEFAULT_BAUD_RATE)))
    port = serial.Serial(port_name, baud, timeout=1.0)
    sensor = AtlasPHSensor(driver=AtlasScientificEZOUart(port))
    log.info("Atlas pH sensor initialised on UART %s @ %d baud", port_name, baud)
    return sensor


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup. Selects real or mock sensor."""
    app = Connector(config)

    if _MOCK:
        log.warning("MOCK MODE - using simulated pH sensor")
        from rxn_bench_ph.mock_ph_sensor import MockPHSensor
        sensor = MockPHSensor()
    else:
        try:
            if _TRANSPORT == "uart":
                sensor = _make_uart_sensor()
            elif _TRANSPORT == "i2c":
                sensor = _make_i2c_sensor()
            else:
                raise RuntimeError(
                    f"Unknown RXN_BENCH_PH_TRANSPORT={_TRANSPORT!r}; use 'i2c' or 'uart'."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to initialise pH sensor: {exc}") from exc

    app.register(PHSensor(sensor=sensor))
    yield app
