"""
SiLA2 server discovery via mDNS. Emits rxnbench_server_found or unknown_server_found
based on whether GetImplementedFeatures returns any /rxnbench/ identifiers.
"""
from __future__ import annotations

import dataclasses
import threading
from typing import Callable

import grpc
from PySide6.QtCore import QObject, Signal
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from .proto import sila_service_pb2 as _ss

# Both service types are scanned simultaneously.
# _sila._tcp.local.  - UniteLabs CDK
# _sila2._tcp.local. - Other vendors may use this
SILA_SERVICE_TYPES = [
    "_sila._tcp.local.",
    "_sila2._tcp.local.",
]

_SS_PATH = (
    "/sila2.org.silastandard.core.silaservice.v1"
    ".SiLAService/Get_ImplementedFeatures"
)


@dataclasses.dataclass
class DiscoveredServer:
    """A SiLA2 server found on the local network."""
    name: str               # human-readable server name from mDNS
    host: str               # IP address
    port: int               # gRPC port
    uuid: str = ""          # SiLA server UUID from mDNS TXT record
    description: str = ""   # from mDNS TXT record
    features: list[str] = dataclasses.field(default_factory=list)

    @property
    def rxnbench_features(self) -> list[str]:
        """Feature identifiers that belong to the rxnbench category."""
        return [f for f in self.features if "/rxnbench/" in f]

    def feature_names(self) -> list[str]:
        """
        Short class names from all feature identifiers on this server,
        excluding the mandatory SiLAService core feature.

        Works for both rxnbench devices and third-party SiLA devices, e.g.:
          edu.iastate.ames/rxnbench/PHSensor/v1  → 'PHSensor'
          org.silastandard/features/PHMeasurement/v1 → 'PHMeasurement'
        """
        names = []
        for f in self.features:
            if "org.silastandard/core/SiLAService" in f:
                continue
            parts = f.split("/")
            if len(parts) >= 3:
                names.append(parts[2])
        return names


class SilaDiscovery(QObject):
    """
    Discovers SiLA2 servers on the local network via mDNS.

    Signals:
        rxnbench_server_found(DiscoveredServer) - server has at least one
            /rxnbench/ feature; goes into the "known devices" list.
        unknown_server_found(DiscoveredServer)   - valid SiLA server but no
            /rxnbench/ features; goes into the "unknown" list.
        server_lost(str) - a previously found server disappeared (either list);
            value is the server's uuid.
    """

    rxnbench_server_found = Signal(object)  # DiscoveredServer
    unknown_server_found   = Signal(object)  # DiscoveredServer
    server_lost            = Signal(str)     # server uuid

    def __init__(self, probe_features: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._probe = probe_features
        self._zc: Zeroconf | None = None
        self._browsers: list[ServiceBrowser] = []
        self._lock = threading.Lock()
        self._known: dict[str, DiscoveredServer] = {}
        self._mdns_to_uuid: dict[str, str] = {}

    def start(self) -> None:
        """Begin continuous mDNS listening on both SiLA service types."""
        if self._zc is not None:
            return
        self._zc = Zeroconf()
        listener = self._make_listener()
        self._browsers = [
            ServiceBrowser(self._zc, stype, listener)
            for stype in SILA_SERVICE_TYPES
        ]

    def stop(self) -> None:
        """Stop listening and release the mDNS socket."""
        if self._zc:
            self._zc.close()
            self._zc = None
            self._browsers = []
        with self._lock:
            self._known.clear()
            self._mdns_to_uuid.clear()

    def probe_manual(self, host: str, port: int) -> None:
        """
        Probe a server at a known host:port without mDNS.

        Use when mDNS is blocked (different subnet, VPN, wired/wireless split).
        Non-blocking - emits rxnbench_server_found or unknown_server_found
        when the probe completes.
        """
        server = DiscoveredServer(
            name=f"{host}:{port}",
            host=host,
            port=port,
            uuid=f"{host}:{port}",  # placeholder until probe fills it in
        )
        threading.Thread(
            target=self._probe_and_emit,
            args=(server, None, None),
            daemon=True,
        ).start()

    def scan(self, timeout: float = 3.0) -> tuple[list[DiscoveredServer], list[DiscoveredServer]]:
        """
        One-shot blocking scan. Listens for `timeout` seconds then returns
        (rxnbench_servers, unknown_servers). Does not emit signals.

        Call in a background thread so the UI stays responsive while scanning.
        """
        rxnbench: dict[str, DiscoveredServer] = {}
        unknown:   dict[str, DiscoveredServer] = {}

        def on_found(server: DiscoveredServer) -> None:
            key = server.uuid or server.name
            if server.rxnbench_features:
                rxnbench[key] = server
            else:
                unknown[key] = server

        zc = Zeroconf()
        listener = self._make_listener(on_found_callback=on_found)
        for stype in SILA_SERVICE_TYPES:
            ServiceBrowser(zc, stype, listener)
        threading.Event().wait(timeout)
        zc.close()
        return list(rxnbench.values()), list(unknown.values())

    @property
    def known_servers(self) -> tuple[list[DiscoveredServer], list[DiscoveredServer]]:
        """Snapshot of (rxnbench_servers, unknown_servers) for continuous mode."""
        with self._lock:
            servers = list(self._known.values())
        rxnbench = [s for s in servers if s.rxnbench_features]
        unknown   = [s for s in servers if not s.rxnbench_features]
        return rxnbench, unknown

    def _make_listener(
        self,
        on_found_callback: Callable[[DiscoveredServer], None] | None = None,
    ) -> ServiceListener:
        """
        Build a zeroconf ServiceListener. If on_found_callback is provided
        (one-shot mode), call it instead of emitting Qt signals.
        """
        discovery = self

        class _Listener(ServiceListener):
            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                info = zc.get_service_info(type_, name, timeout=3000)
                if info is None:
                    return

                addrs = info.parsed_addresses()
                host = addrs[0] if addrs else str(info.server).rstrip(".")
                port = info.port

                props: dict[str, str] = {}
                for k, v in (info.properties or {}).items():
                    key = k.decode() if isinstance(k, bytes) else k
                    val = v.decode() if isinstance(v, bytes) else (v or "")
                    props[key] = val

                # CDK TXT record uses "server_name"; the UUID is the mDNS
                # service instance name with the service type suffix stripped.
                # Works for both _sila._tcp and _sila2._tcp suffixes.
                mDNS_uuid = name.split("._sila")[0]
                uuid = props.get("uuid", mDNS_uuid)

                # Deduplicate: if this UUID was already found via the other
                # service type, skip - don't emit a duplicate signal.
                with discovery._lock:
                    if uuid in discovery._known:
                        discovery._mdns_to_uuid[name] = uuid
                        return

                server = DiscoveredServer(
                    name=props.get("server_name", mDNS_uuid),
                    host=host,
                    port=port,
                    uuid=uuid,
                    description=props.get("description", ""),
                )

                if discovery._probe:
                    threading.Thread(
                        target=discovery._probe_and_emit,
                        args=(server, name, on_found_callback),
                        daemon=True,
                    ).start()
                else:
                    discovery._register(server, name, on_found_callback)

            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                with discovery._lock:
                    uuid = discovery._mdns_to_uuid.pop(name, None)
                    if uuid:
                        # Only remove if no other mDNS name still points to it
                        still_alive = any(
                            v == uuid for v in discovery._mdns_to_uuid.values()
                        )
                        server = None if still_alive else discovery._known.pop(uuid, None)
                    else:
                        server = None
                if server and on_found_callback is None:
                    discovery.server_lost.emit(server.uuid)

            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                pass

        return _Listener()

    def _probe_and_emit(
        self,
        server: DiscoveredServer,
        mDNS_name: str,
        callback: Callable[[DiscoveredServer], None] | None,
    ) -> None:
        """Fetch GetImplementedFeatures from the server, then register/emit."""
        channel = grpc.insecure_channel(f"{server.host}:{server.port}")
        try:
            raw = channel.unary_unary(_SS_PATH)(b"", timeout=3.0)
            resp = _ss.Get_ImplementedFeatures_Responses.FromString(bytes(raw))
            server.features = [item.value for item in resp.ImplementedFeatures]
        except Exception:
            pass
        finally:
            channel.close()

        self._register(server, mDNS_name, callback)

    def _register(
        self,
        server: DiscoveredServer,
        mDNS_name: str | None,
        callback: Callable[[DiscoveredServer], None] | None,
    ) -> None:
        with self._lock:
            self._known[server.uuid] = server
            if mDNS_name is not None:
                self._mdns_to_uuid[mDNS_name] = server.uuid
        if callback is not None:
            callback(server)
        elif server.rxnbench_features:
            self.rxnbench_server_found.emit(server)
        else:
            self.unknown_server_found.emit(server)
