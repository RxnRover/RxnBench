"""
SiLA server app factory - Camera device.

Start with: rxn-bench-camera
"""
import logging
import os

from unitelabs.cdk.connector import Connector

from rxn_bench_camera.camera_config import CameraConfig
from rxn_bench_camera.feature import Camera

log = logging.getLogger(__name__)

_MOCK = bool(os.environ.get("RXN_BENCH_MOCK"))


async def create_app(config):
    """App factory called by the UniteLabs CDK at startup. Selects real or mock camera."""
    app = Connector(config)
    machine = CameraConfig.load()

    if _MOCK:
        log.warning("MOCK MODE - using simulated camera")
        from rxn_bench_camera.mock_camera import MockCamera
        camera = MockCamera()
    else:
        from rxn_bench_camera.crowsnest_camera import CrowsnestCamera
        camera = CrowsnestCamera(machine.crowsnest_base_url, machine.crowsnest_snapshot_path)
        log.info("Crowsnest camera configured at %s", machine.crowsnest_base_url)

    app.register(Camera(camera=camera, capture_interval_s=machine.capture_interval_s))
    yield app
