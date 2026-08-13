"""
Crowsnest camera driver, registered under the "rxn_bench.camera_drivers"
entry-point group (see rxn_bench_camera.server, the capability package this
driver implements CameraProtocol for).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def build_camera(base_url: str, snapshot_path: str):
    """Entry point loaded by rxn_bench_camera.server as the "crowsnest" driver."""
    from rxn_bench_crowsnest_camera_driver.crowsnest_camera import CrowsnestCamera
    camera = CrowsnestCamera(base_url, snapshot_path)
    log.info("Crowsnest camera configured at %s", base_url)
    return camera
