"""
Zero-boilerplate device auto-discovery for RxnBenchClient.

``bench.devices.<name>`` finds and connects an instrument automatically,
instead of the explicit ``bench.connect(name, cls, server=...)`` dance::

    with RxnBenchClient() as bench:
        bench.devices.gantry.mount_toolhead("ph_probe")
        bench.devices.pump.set_flow_rate(2.0)
"""

from __future__ import annotations

import time
from typing import Any

from sila2.client import SilaClient

from .instruments import Camera, DosingPump, Gantry, PHProbe

# name -> (wrapper class, SiLA feature identifier it requires)
DEVICE_REGISTRY: dict[str, tuple[type, str]] = {
    "gantry": (Gantry, "Gantry"),
    "ph": (PHProbe, "PHSensor"),
    "camera": (Camera, "Camera"),
    "pump": (DosingPump, "DosingPump"),
}


def discover_sila_clients(timeout: float = 5.0) -> list[SilaClient]:
    """Return a connected SilaClient for every SiLA server found on the network.

    Each returned client already has its advertised features probed and
    exposed as attributes (``client.DosingPump``, ``client.PHSensor``, ...)
    - that's ``sila2.client.SilaClient``'s own behavior, not something this
    function adds.
    """
    from sila2.discovery.browser import SilaDiscoveryBrowser

    with SilaDiscoveryBrowser(insecure=True) as browser:
        time.sleep(timeout)
        return list(browser.clients)


def _describe(sila: SilaClient) -> str:
    try:
        name = sila.SiLAService.ServerName.get()
    except Exception:
        name = "?"
    return f"{name!r} at {sila.address}:{sila.port}"


class DeviceNamespace:
    """``bench.devices`` - see module docstring."""

    def __init__(self, bench: Any) -> None:
        self._bench = bench
        self._clients: list[SilaClient] | None = None

    def _scan(self) -> list[SilaClient]:
        if self._clients is None:
            self._clients = discover_sila_clients()
        return self._clients

    def _match(self, feature: str) -> list[SilaClient]:
        return [c for c in self._scan() if hasattr(c, feature)]

    def __getattr__(self, name: str) -> Any:
        if name not in DEVICE_REGISTRY:
            raise AttributeError(
                f"No built-in device named {name!r}. Known: {sorted(DEVICE_REGISTRY)}. "
                "For anything else, use bench.connect(...) or bench.devices.raw(feature_name)."
            )
        if hasattr(self._bench, name):
            # Already attached, whether via an earlier bench.devices.<name>
            # access or an explicit bench.connect(name, ...) - reuse it
            # instead of reconnecting and rewrapping on every access.
            return getattr(self._bench, name)
        cls, feature = DEVICE_REGISTRY[name]
        matches = self._match(feature)
        if not matches:
            raise RuntimeError(
                f"No server advertising the {feature!r} feature was found on the network. "
                "Is it running? Or connect explicitly: bench.connect(...)."
            )
        if len(matches) > 1:
            candidates = ", ".join(_describe(c) for c in matches)
            raise RuntimeError(
                f"Multiple servers advertise {feature!r}: {candidates}. "
                "Disambiguate with bench.connect(name, cls, host=..., port=...)."
            )
        self._bench._attach(name, cls, matches[0])
        return getattr(self._bench, name)

    def raw(self, feature_name: str) -> Any:
        """Discover a server by SiLA feature name and return the raw feature
        proxy, with no wrapper class involved.

        For a device that isn't built already into the DEVICE_REGISTRY -
        no Instrument class to write, no registry entry to add::

            bench.devices.raw("Spectrometer").Read(Wavelength=600)
        """
        matches = self._match(feature_name)
        if not matches:
            raise RuntimeError(
                f"No server advertising the {feature_name!r} feature was found on the network."
            )
        if len(matches) > 1:
            candidates = ", ".join(_describe(c) for c in matches)
            raise RuntimeError(
                f"Multiple servers advertise {feature_name!r}: {candidates}. "
                "Connect explicitly instead: sila2.client.SilaClient(host, port)."
            )
        sila = matches[0]
        self._bench._instrument_clients.append(sila)
        return getattr(sila, feature_name)

    def __dir__(self) -> list[str]:
        return sorted(DEVICE_REGISTRY)
