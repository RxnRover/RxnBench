#!/usr/bin/env python3
"""
Scan the local network for SiLA2 servers and print what's found.

Run from the repo root:
    cd software/frontend
    uv run python scripts/scan_sila.py
    uv run python scripts/scan_sila.py --timeout 5
    uv run python scripts/scan_sila.py --no-probe        # skip GetImplementedFeatures
    uv run python scripts/scan_sila.py --manual 192.168.1.42:50051
"""
import argparse
import sys
import threading

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
import grpc

SILA_SERVICE_TYPES = [
    "_sila._tcp.local.",    # UniteLabs CDK (confirmed)
    "_sila2._tcp.local.",   # SiLA2 spec; other vendors may use this
]
_SS_PATH = (
    "/sila2.org.silastandard.core.silaservice.v1"
    ".SiLAService/Get_ImplementedFeatures"
)


def _probe_features(host: str, port: int) -> list[str]:
    channel = grpc.insecure_channel(f"{host}:{port}")
    try:
        # Import here so the script works without the full frontend package installed
        sys.path.insert(0, "src")
        from rxn_bench_ui.proto import sila_service_pb2 as _ss
        raw = channel.unary_unary(_SS_PATH)(b"", timeout=3.0)
        resp = _ss.Get_ImplementedFeatures_Responses.FromString(bytes(raw))
        return [item.value for item in resp.ImplementedFeatures]
    except Exception as e:
        return [f"(probe failed: {e})"]
    finally:
        channel.close()


def scan(timeout: float, probe: bool) -> None:
    found = {}
    lock = threading.Lock()

    class _Listener(ServiceListener):
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, timeout=3000)
            if info is None:
                return

            addrs = info.parsed_addresses()
            host = addrs[0] if addrs else str(info.server).rstrip(".")
            port = info.port

            props = {}
            for k, v in (info.properties or {}).items():
                key = k.decode() if isinstance(k, bytes) else k
                val = v.decode() if isinstance(v, bytes) else (v or "")
                props[key] = val

            mDNS_uuid   = name.split("._sila")[0]
            server_name = props.get("server_name", mDNS_uuid)
            uuid        = props.get("uuid", mDNS_uuid)
            description = props.get("description", "")

            features = _probe_features(host, port) if probe else []

            with lock:
                if uuid in {v["uuid"] for v in found.values()}:
                    return  # already found via the other service type
                found[name] = {
                    "name":        server_name,
                    "host":        host,
                    "port":        port,
                    "uuid":        uuid,
                    "description": description,
                    "features":    features,
                }

            print(f"\n  Found: {server_name}")
            print(f"    Host:        {host}:{port}")
            print(f"    UUID:        {uuid}")
            if description:
                print(f"    Description: {description}")
            if features:
                for f in features:
                    tag = "  [rxnbench]" if "/rxnbench/" in f else ""
                    print(f"    Feature:     {f}{tag}")

        def remove_service(self, zc, type_, name):
            pass

        def update_service(self, zc, type_, name):
            pass

    print(f"Scanning for SiLA2 servers ({timeout}s, both _sila._tcp and _sila2._tcp)...")
    zc = Zeroconf()
    listener = _Listener()
    for stype in SILA_SERVICE_TYPES:
        ServiceBrowser(zc, stype, listener)

    try:
        threading.Event().wait(timeout)
    except KeyboardInterrupt:
        pass
    finally:
        zc.close()

    print(f"\n{'─' * 40}")
    print(f"Found {len(found)} server(s).")
    if not found:
        print(
            "\nNothing found. Make sure:\n"
            "  • The SiLA server is running (rxn-bench-gantry / rxn-bench-ph)\n"
            "  • Both machines are on the same subnet\n"
            "  • mDNS / Bonjour is not blocked by a firewall\n"
            "\nIf mDNS is blocked (different VLAN, VPN, wired/WiFi split) use:\n"
            "  uv run python scripts/scan_sila.py --manual 192.168.1.42:50051\n"
            "\nTo test locally run a server in mock mode first:\n"
            "  RXN_BENCH_MOCK=1 rxn-bench-gantry"
        )


def probe_manual(host: str, port: int, probe: bool) -> None:
    """Probe a single server at a known host:port, bypassing mDNS."""
    print(f"Probing {host}:{port} directly...")
    features = _probe_features(host, port) if probe else []
    print(f"\n  Found: {host}:{port}")
    if features:
        for f in features:
            tag = "  [rxnbench]" if "/rxnbench/" in f else ""
            print(f"    Feature: {f}{tag}")
    else:
        print("    (no features returned or probe skipped)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan for SiLA2 servers on the local network.")
    parser.add_argument("--timeout", type=float, default=3.0, help="Scan duration in seconds (default 3)")
    parser.add_argument("--no-probe", action="store_true", help="Skip GetImplementedFeatures probe")
    parser.add_argument(
        "--manual", metavar="HOST:PORT",
        help="Skip mDNS and probe a specific host:port directly (e.g. 192.168.1.42:50051)"
    )
    args = parser.parse_args()

    if args.manual:
        try:
            host, port_str = args.manual.rsplit(":", 1)
            probe_manual(host, int(port_str), probe=not args.no_probe)
        except ValueError:
            print(f"Error: --manual expects HOST:PORT, got: {args.manual}")
            sys.exit(1)
    else:
        scan(timeout=args.timeout, probe=not args.no_probe)
