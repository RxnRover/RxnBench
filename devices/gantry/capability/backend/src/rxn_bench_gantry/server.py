"""
SiLA server app factory - Gantry device.

Start with: rxn-bench-gantry

RXN_BENCH_MOCK=1 selects a simulated motion client (MockMoonrakerClient - a
generic in-memory simulator of MotionClientProtocol, not tied to any real
motion controller's wire format, so it stays in this capability package).
Otherwise, the real driver is loaded via the "rxn_bench.gantry_drivers"
entry-point group - RXN_BENCH_GANTRY_DRIVER picks which registered driver to
use (default: "moonraker", provided by the rxn-bench-moonraker-driver
package). This capability package has no import-time dependency on any
concrete motion controller driver.
"""
import importlib.metadata
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_gantry.machine_config import MachineConfig
from rxn_bench_gantry.controller import GantryController
from rxn_bench_gantry.feature import Gantry

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))
_DRIVER_NAME = os.environ.get("RXN_BENCH_GANTRY_DRIVER", "moonraker")
_DRIVER_GROUP = "rxn_bench.gantry_drivers"


def _load_driver_factory(name: str):
    for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP):
        if ep.name == name:
            return ep.load()
    available = sorted(ep.name for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP))
    raise RuntimeError(
        f"No gantry driver registered as {name!r} under the {_DRIVER_GROUP!r} entry-point "
        f"group; available: {available or '(none installed)'}"
    )


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup.

    Args:
        config: CDK configuration object injected by the framework.
    """
    app = Connector(config)
    machine = MachineConfig.load()

    if _MOCK:
        log.warning("MOCK MODE - using simulated motion hardware")
        from rxn_bench_gantry.mock_moonraker import MockMoonrakerClient
        motion_client = MockMoonrakerClient()
    else:
        build_motion_client = _load_driver_factory(_DRIVER_NAME)
        motion_client = await build_motion_client(machine.moonraker_fallback_host)

    # get_axis_limits() gives the starting *size* of each axis (Klipper's
    # configured travel range, or the mock's fixed bed). Only the span
    # (max - min) is used, never Klipper's raw absolute numbering: this app
    # assumes a 0-based frame everywhere (workspace YAML, plate origins,
    # HomingManager.confirm_x_min/y_min), so min is always forced to 0 here
    # even when Klipper's position_min is negative. This is only the initial
    # default - manual homing and its saved state take precedence once
    # calibrated. Falls back to conservative defaults if the query fails so a
    # slow motion controller doesn't take the whole server down.
    try:
        limits = motion_client.get_axis_limits()
        x_min, x_max = 0.0, limits["x"][1] - limits["x"][0]
        y_min, y_max = 0.0, limits["y"][1] - limits["y"][0]
        z_min, z_max = 0.0, limits["z"][1] - limits["z"][0]
    except Exception as exc:
        log.warning("Could not query axis limits (%s) - using conservative defaults.", exc)
        x_min, x_max = 0.0, 350.0
        y_min, y_max = 0.0, 350.0
        z_min, z_max = 0.0, 340.0

    controller = GantryController(
        client=motion_client,
        x_min=x_min, x_max=x_max,
        y_min=y_min, y_max=y_max,
        z_min=z_min, z_max=z_max,
        z_clearance_padding_mm=machine.z_clearance_padding_mm,
        engage_bottom_margin_mm=machine.engage_bottom_margin_mm,
        crossbar_clearance_above_tip_mm=machine.crossbar_clearance_above_tip_mm,
        crossbar_y_thickness_mm=machine.crossbar_y_thickness_mm,
    )

    app.register(Gantry(controller=controller))
    yield app
