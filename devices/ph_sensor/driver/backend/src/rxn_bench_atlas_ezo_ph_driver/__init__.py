"""
Atlas Scientific EZO-pH driver, registered under the "rxn_bench.ph_drivers"
entry-point group (see rxn_bench_ph.server, the capability package this
driver implements PHSensorProtocol for).

Transport is chosen at startup by environment variables, mirroring RXN_BENCH_MOCK:
    RXN_BENCH_PH_TRANSPORT=i2c   - Atlas EZO-pH over I2C (default)
    RXN_BENCH_PH_TRANSPORT=uart  - Atlas EZO-pH over UART/serial
        RXN_BENCH_PH_SERIAL_PORT=/dev/serial0   (default)
        RXN_BENCH_PH_BAUD=9600                  (default; EZO UART default)
    RXN_BENCH_PH_I2C_BUS=1       - I2C bus number (default)

Set these in the systemd unit (e.g. `sudo systemctl edit rxn-bench-ph` ->
[Service] Environment=RXN_BENCH_PH_TRANSPORT=uart).
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def _make_i2c_sensor():
    """Build an AtlasPHSensor talking to the EZO-pH over I2C."""
    try:
        from smbus2 import SMBus
        from rxn_bench_atlas_ezo_ph_driver.atlas_ph_sensor import AtlasPHSensor
        from rxn_bench_atlas_ezo_ph_driver.i2c_bus import SMBusI2C
    except ImportError:
        raise RuntimeError(
            "smbus2 is required to run the pH sensor server over I2C. "
            "Install with: pip install rxn-bench-atlas-ezo-ph-driver[rpi]"
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
        from rxn_bench_atlas_ezo_ph_driver.atlas_ph_sensor import AtlasPHSensor
        from rxn_bench_atlas_ezo_ph_driver.atlas_scientific_uart_driver import (
            AtlasScientificEZOUart,
            DEFAULT_BAUD_RATE,
        )
    except ImportError:
        raise RuntimeError(
            "pyserial is required to run the pH sensor server over UART. "
            "Install with: pip install rxn-bench-atlas-ezo-ph-driver[rpi]"
        )
    port_name = os.environ.get("RXN_BENCH_PH_SERIAL_PORT", "/dev/serial0")
    baud = int(os.environ.get("RXN_BENCH_PH_BAUD", str(DEFAULT_BAUD_RATE)))
    port = serial.Serial(port_name, baud, timeout=1.0)
    sensor = AtlasPHSensor(driver=AtlasScientificEZOUart(port))
    log.info("Atlas pH sensor initialised on UART %s @ %d baud", port_name, baud)
    return sensor


def build_sensor():
    """Entry point loaded by rxn_bench_ph.server as the "atlas_ezo" driver."""
    transport = os.environ.get("RXN_BENCH_PH_TRANSPORT", "i2c").lower()
    if transport == "uart":
        return _make_uart_sensor()
    elif transport == "i2c":
        return _make_i2c_sensor()
    else:
        raise RuntimeError(f"Unknown RXN_BENCH_PH_TRANSPORT={transport!r}; use 'i2c' or 'uart'.")
