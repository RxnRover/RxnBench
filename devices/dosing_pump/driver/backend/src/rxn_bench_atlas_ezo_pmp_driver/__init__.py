"""
Atlas Scientific EZO-PMP dosing pump driver, registered under the
"rxn_bench.dosing_pump_drivers" entry-point group (see rxn_bench_dosing_pump.server,
the capability package this driver implements DosingPumpProtocol for).

RXN_BENCH_PUMP_SERIAL_PORT=/dev/serial0   (default)
RXN_BENCH_PUMP_BAUD=9600                  (default; EZO UART default)
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def build_pump():
    """Entry point loaded by rxn_bench_dosing_pump.server as the "atlas_ezo_pmp" driver."""
    try:
        import serial
        from rxn_bench_atlas_ezo_pmp_driver.atlas_dosing_pump import AtlasDosingPump
        from rxn_bench_atlas_ezo_pmp_driver.atlas_scientific_uart_driver import (
            AtlasScientificEZOPumpUart,
            DEFAULT_BAUD_RATE,
        )
    except ImportError:
        raise RuntimeError(
            "pyserial is required to run the dosing pump server over UART. "
            "Install with: pip install rxn-bench-atlas-ezo-pmp-driver[rpi]"
        )
    port_name = os.environ.get("RXN_BENCH_PUMP_SERIAL_PORT", "/dev/serial0")
    baud = int(os.environ.get("RXN_BENCH_PUMP_BAUD", str(DEFAULT_BAUD_RATE)))
    port = serial.Serial(port_name, baud, timeout=1.0)
    pump = AtlasDosingPump(AtlasScientificEZOPumpUart(port))
    log.info("Atlas EZO-PMP dosing pump initialised on UART %s @ %d baud", port_name, baud)
    return pump


def build_mock_pump():
    """The RXN_BENCH_MOCK=1 path: same driver stack over a protocol emulator, not a
    generic no-hardware stub - see mock_device.MockDosingPump's docstring for why."""
    from rxn_bench_atlas_ezo_pmp_driver.mock_device import MockDosingPump
    return MockDosingPump()
