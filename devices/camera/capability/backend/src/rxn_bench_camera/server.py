"""
SiLA server app factory - Camera device.

Start with: rxn-bench-camera

RXN_BENCH_MOCK=1 selects a simulated camera, no hardware. Otherwise, the real
driver is loaded via the "rxn_bench.camera_drivers" entry-point group -
RXN_BENCH_CAMERA_DRIVER picks which registered driver to use (default:
"crowsnest", provided by the rxn-bench-crowsnest-camera-driver package). This
capability package has no import-time dependency on any concrete driver - a
future direct-USB camera driver registers under the same entry-point group
without any change here.
"""
import importlib.metadata
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_camera.camera_config import CameraConfig
from rxn_bench_camera.feature import Camera

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))
_DRIVER_NAME = os.environ.get("RXN_BENCH_CAMERA_DRIVER", "crowsnest")
_DRIVER_GROUP = "rxn_bench.camera_drivers"


def _load_driver_factory(name: str):
    for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP):
        if ep.name == name:
            return ep.load()
    available = sorted(ep.name for ep in importlib.metadata.entry_points(group=_DRIVER_GROUP))
    raise RuntimeError(
        f"No camera driver registered as {name!r} under the {_DRIVER_GROUP!r} entry-point "
        f"group; available: {available or '(none installed)'}"
    )


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup. Selects real or mock camera."""
    app = Connector(config)
    machine = CameraConfig.load()

    if _MOCK:
        log.warning("MOCK MODE - using simulated camera")
        from rxn_bench_camera.mock_camera import MockCamera
        camera = MockCamera()
    else:
        build_camera = _load_driver_factory(_DRIVER_NAME)
        camera = build_camera(machine.crowsnest_base_url, machine.crowsnest_snapshot_path)

    app.register(Camera(camera=camera, capture_interval_s=machine.capture_interval_s))
    yield app
