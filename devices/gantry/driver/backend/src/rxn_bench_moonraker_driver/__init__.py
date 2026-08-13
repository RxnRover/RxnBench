"""
Moonraker/Klipper motion driver, registered under the "rxn_bench.gantry_drivers"
entry-point group (see rxn_bench_gantry.server, the capability package this
driver implements MotionClientProtocol for).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


async def build_motion_client(fallback_host: str, default_speed: float = 4500.0):
    """Entry point loaded by rxn_bench_gantry.server as the "moonraker" driver.

    Discovers Moonraker via mDNS (10s timeout), falling back to fallback_host
    if not found.
    """
    from rxn_bench_moonraker_driver.moonraker_client import MoonrakerClient
    from rxn_bench_moonraker_driver.moonraker_discovery import find_moonraker

    log.info("Searching for Moonraker...")
    host = await find_moonraker(timeout=10.0)
    if host:
        log.info("Moonraker found at %s", host)
    else:
        host = fallback_host
        log.warning("Moonraker not discovered - falling back to %s", host)
    return MoonrakerClient(host, default_speed=default_speed)
