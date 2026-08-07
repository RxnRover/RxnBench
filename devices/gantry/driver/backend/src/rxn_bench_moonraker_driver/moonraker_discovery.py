"""
Discovers Moonraker via mDNS (_moonraker._tcp) or IPv6 link-local scan in parallel.
Returns the first host that responds on port 7125.
"""
import asyncio
import logging
import socket
import subprocess
import time

from zeroconf import ServiceBrowser, Zeroconf

log = logging.getLogger(__name__)

MOONRAKER_PORT = 7125
MOONRAKER_SERVICE = "_moonraker._tcp.local."


def _probe_port(host: str, port: int = MOONRAKER_PORT, timeout: float = 2.0) -> bool:
    """Return True if something is listening on host:port."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def _probe_ipv6_link_local(addr: str, iface: str, port: int = MOONRAKER_PORT) -> bool:
    """Return True if Moonraker is reachable at an IPv6 link-local address."""
    try:
        scope_id = socket.if_nametoindex(iface)
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect((addr, port, 0, scope_id))
        sock.close()
        return True
    except Exception:
        return False


def _mdns_scan(timeout: float = 3.0) -> str | None:
    """Scan for _moonraker._tcp via mDNS. Returns IPv4 address string or None."""
    found: list[str] = []

    class Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name)
            if info and info.addresses:
                addr = socket.inet_ntoa(info.addresses[0])
                log.info("mDNS: found Moonraker at %s", addr)
                found.append(addr)

        def remove_service(self, *_): pass
        def update_service(self, *_): pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, MOONRAKER_SERVICE, Listener())
        time.sleep(timeout)
    finally:
        zc.close()

    return found[0] if found else None


def _link_local_scan(timeout: float = 3.0) -> str | None:
    """
    Scan Ethernet interfaces for IPv6 link-local neighbors running Moonraker.

    Pings the all-nodes multicast to populate the neighbor table, then probes
    each fe80:: neighbor on port 7125. Works with a direct cable and zero IP config.
    """
    # Find Ethernet-like interfaces that are UP (skip loopback and WiFi)
    try:
        result = subprocess.run(
            ["ip", "-o", "link", "show", "up"],
            capture_output=True, text=True, timeout=3,
        )
        interfaces = []
        for line in result.stdout.splitlines():
            if "LOOPBACK" in line:
                continue
            iface = line.split()[1].rstrip(":")
            if iface.startswith(("lo", "wl", "virbr", "docker", "br-")):
                continue
            interfaces.append(iface)
    except Exception:
        return None

    for iface in interfaces:
        subprocess.run(
            ["ping6", "-c", "2", "-W", "1", f"ff02::1%{iface}"],
            capture_output=True, timeout=5,
        )

        try:
            result = subprocess.run(
                ["ip", "neigh", "show", "dev", iface],
                capture_output=True, text=True, timeout=3,
            )
        except Exception:
            continue

        for line in result.stdout.splitlines():
            if "fe80::" not in line.lower():
                continue
            state = line.upper()
            if not any(s in state for s in ("REACHABLE", "STALE", "DELAY", "PROBE")):
                continue
            addr = line.split()[0]
            if _probe_ipv6_link_local(addr, iface):
                host = f"[{addr}%25{iface}]"
                log.info("Link-local: found Moonraker at %s", host)
                return host

    return None


async def find_moonraker(timeout: float = 5.0) -> str | None:
    """
    Discover a Moonraker instance and return its host string, or None.

    Runs mDNS and IPv6 link-local scans in parallel and returns whichever
    finds something first. Pass the result directly to MoonrakerClient as host.
    """
    loop = asyncio.get_event_loop()
    half = timeout / 2

    mdns = loop.run_in_executor(None, _mdns_scan, half)
    link = loop.run_in_executor(None, _link_local_scan, half)

    for coro in asyncio.as_completed([mdns, link]):
        result = await coro
        if result:
            return result

    return None
