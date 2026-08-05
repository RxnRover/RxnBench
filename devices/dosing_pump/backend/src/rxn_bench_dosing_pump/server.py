"""
SiLA server app factory - dosing pump device.

Start with: rxn-bench-dosing-pump

Configured by environment variables, mirroring the pH sensor's UART path:
    RXN_BENCH_MOCK=1                     - simulated pump, no hardware
    RXN_BENCH_PUMP_SERIAL_PORT=/dev/serial0   (default)
    RXN_BENCH_PUMP_BAUD=9600                  (default; EZO UART default)

NOTE ON SERIAL PORT CONTENTION: the reference bench already runs the EZO-pH
circuit on the Pi's primary UART (/dev/ttyAMA0 via /dev/serial0), so the pump
needs its own port - a second PL011 enabled via a `dtoverlay=uartN` line in
/boot/firmware/config.txt, or a USB-serial adapter. Set
RXN_BENCH_PUMP_SERIAL_PORT accordingly; leaving both devices on serial0 will
have them fighting over the same bytes.

The reference bench (Pi 5) uses `dtoverlay=uart2` in config.txt, which brings
up UART2 on GPIO4/5 (TXD2/RXD2) as /dev/ttyAMA2 - confirmed against the real
EZO-PMP on 2026-08-04 (device info, status, and PV,? all responded correctly).
install_service.sh sets this automatically for the `pump` device; set it by
hand elsewhere via `sudo systemctl edit rxn-bench-dosing-pump` ->
[Service] Environment=RXN_BENCH_PUMP_SERIAL_PORT=/dev/ttyAMA2.
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_dosing_pump.feature import DosingPump

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))
# Which pump model to drive. The feature and the whole frontend depend only on
# DosingPumpProtocol, so a second model is a new builder registered in
# _DRIVERS below - not a change to the feature, proto, client, or widget.
_DRIVER = os.environ.get("RXN_BENCH_PUMP_DRIVER", "atlas_ezo_pmp").lower()


def _make_uart_pump():
    """Build an AtlasDosingPump talking to the EZO-PMP over UART/serial."""
    try:
        import serial
        from rxn_bench_dosing_pump.atlas_dosing_pump import AtlasDosingPump
        from rxn_bench_dosing_pump.atlas_scientific_uart_driver import (
            AtlasScientificEZOPumpUart,
            DEFAULT_BAUD_RATE,
        )
    except ImportError:
        raise RuntimeError(
            "pyserial is required to run the dosing pump server over UART. "
            "Install with: pip install rxn-bench-dosing-pump[rpi]"
        )
    port_name = os.environ.get("RXN_BENCH_PUMP_SERIAL_PORT", "/dev/serial0")
    baud = int(os.environ.get("RXN_BENCH_PUMP_BAUD", str(DEFAULT_BAUD_RATE)))
    port = serial.Serial(port_name, baud, timeout=1.0)
    pump = AtlasDosingPump(AtlasScientificEZOPumpUart(port))
    log.info("Atlas EZO-PMP dosing pump initialised on UART %s @ %d baud", port_name, baud)
    return pump


# Pump models this server can drive, keyed by RXN_BENCH_PUMP_DRIVER. Each
# builder returns something satisfying DosingPumpProtocol; nothing above this
# line knows which model is attached. Adding a pump = one entry here plus its
# driver module.
_DRIVERS = {
    "atlas_ezo_pmp": _make_uart_pump,
}


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup. Selects real or mock pump."""
    app = Connector(config)

    if _MOCK:
        log.warning("MOCK MODE - using simulated dosing pump")
        from rxn_bench_dosing_pump.mock_device import MockDosingPump
        pump = MockDosingPump()
    else:
        builder = _DRIVERS.get(_DRIVER)
        if builder is None:
            raise RuntimeError(
                f"Unknown RXN_BENCH_PUMP_DRIVER={_DRIVER!r}; "
                f"use one of: {', '.join(sorted(_DRIVERS))}."
            )
        try:
            pump = builder()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialise dosing pump ({_DRIVER}): {exc}\n"
                "Check the serial wiring and run with RXN_BENCH_MOCK=1 to bypass."
            ) from exc

    app.register(DosingPump(pump=pump))
    yield app
