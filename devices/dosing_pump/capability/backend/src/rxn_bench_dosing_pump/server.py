"""
SiLA server app factory - dosing pump device.

Start with: rxn-bench-dosing-pump

RXN_BENCH_MOCK=1 selects a simulated pump, no hardware. Otherwise, the real
driver is loaded via the "rxn_bench.dosing_pump_drivers" entry-point group -
RXN_BENCH_PUMP_DRIVER picks which registered driver to use (default:
"atlas_ezo_pmp", provided by the rxn-bench-atlas-ezo-pmp-driver package; its
own environment variables, e.g. RXN_BENCH_PUMP_SERIAL_PORT, configure that
specific driver). This capability package has no import-time dependency on
any concrete driver - the feature, proto, client, and Qt widget all depend
only on DosingPumpProtocol, so a second pump model registers under the same
entry-point group without any change here.

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
import importlib.metadata
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_dosing_pump.feature import DosingPump

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))
_DRIVER_NAME = os.environ.get("RXN_BENCH_PUMP_DRIVER", "atlas_ezo_pmp")
_DRIVER_GROUP = "rxn_bench.dosing_pump_drivers"


def _load_driver_factory(name: str):
    for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP):
        if ep.name == name:
            return ep.load()
    available = sorted(ep.name for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP))
    raise RuntimeError(
        f"No dosing pump driver registered as {name!r} under the {_DRIVER_GROUP!r} "
        f"entry-point group; available: {available or '(none installed)'}"
    )


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup. Selects real or mock pump."""
    app = Connector(config)

    if _MOCK:
        log.warning("MOCK MODE - using simulated dosing pump")
        # The mock is provided by the default driver package too (it's built on
        # the real Atlas driver stack over a protocol emulator, not a generic
        # no-hardware stub - see rxn_bench_atlas_ezo_pmp_driver.mock_device),
        # so it's loaded the same way as the real driver, just a different
        # registered callable.
        build_mock = _load_driver_factory(f"{_DRIVER_NAME}_mock")
        pump = build_mock()
    else:
        try:
            build_pump = _load_driver_factory(_DRIVER_NAME)
            pump = build_pump()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialise dosing pump ({_DRIVER_NAME}): {exc}\n"
                "Check the serial wiring and run with RXN_BENCH_MOCK=1 to bypass."
            ) from exc

    app.register(DosingPump(pump=pump))
    yield app
