# Deployment (Raspberry Pi backend)

This is the IT/ops-facing companion to [usage.md](usage.md): how to take a fresh
Raspberry Pi to a running, offline, reboot-surviving Rxn Bench backend with one
install command.

## What ships on the Pi

- `rxn-bench-gantry`, `rxn-bench-ph`, and `rxn-bench-camera` - independent
  SiLA2 gRPC servers, one per device, each in its own venv, each its own
  systemd service.
- Nothing else. No database, no message broker, no container runtime.

## Network footprint

| Traffic               | Direction        | Port                   | Notes                                                                                                       |
| --------------------- | ---------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| Gantry SiLA/gRPC      | inbound          | `50051/tcp`            | plaintext (no TLS/auth - assumes an isolated bench network, see [CURRENT_STATE.md](ai/CURRENT_STATE.md) §6) |
| pH sensor SiLA/gRPC   | inbound          | `50052/tcp`            | plaintext, same as above                                                                                    |
| Camera SiLA/gRPC      | inbound          | `50053/tcp`            | plaintext, same as above                                                                                    |
| mDNS/DNS-SD discovery | inbound+outbound | `5353/udp` (multicast) | broadcast by the SiLA2 CDK itself - no separate avahi/mDNS service needed                                   |

Port registry, so the next device doesn't collide (this bit us once already -
`camera` and `device_template` both hardcoded `50053`):

| Device                                              | Port           |
| --------------------------------------------------- | -------------- |
| gantry                                              | 50051          |
| ph_sensor                                           | 50052          |
| camera                                              | 50053          |
| next new device                                     | 50054, then up |
| device_template (scaffold, never run in production) | 50099          |

If a firewall (`ufw`) is active on the Pi, `install_offline.sh` opens the
ports above for whichever devices you install; if `ufw` isn't installed or
isn't active (the common case for a bench Pi), it's a no-op.

## One-time: flash the Pi

Use the official [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
on any machine (this step needs internet once, to fetch the OS image):

1. Choose **Raspberry Pi OS Lite (64-bit)**.
2. Open the imager's advanced options (gear icon) and set hostname, enable
   SSH, and set a username/password - all offline, baked into the image
   before it's ever booted.
3. Flash, boot the Pi, `ssh` in.

## Build the offline bundle (dev machine, has internet)

From `rxnbench/backend`:

```bash
scripts/build_offline_bundle.sh
```

This resolves and downloads every dependency wheel for aarch64/Python 3.13
(from PyPI, [piwheels.org](https://www.piwheels.org) for prebuilt ARM wheels,
and the private UniteLabs index), vendors a matching `uv` binary, and packages
the repo source + wheelhouse + `uv` into one tarball under `dist/`:

```
rxn-bench-backend-offline-<date>-linux_aarch64.tar.gz
```

Override the target platform/Python version with env vars if the Pi's OS
differs (`PYTHON_VERSION`, `PLATFORM_TAG`, `PIP_PLATFORM_TAG`, `UV_TARGET`,
`UV_VERSION`) - see the script header.

## Install on the Pi (no network required)

Copy the tarball over (USB drive, `scp`, whatever's easiest), for example

``` bash
scp rxnbench/backend/dist/rxn-bench-backend-offline-20260710-linux_aarch64.tar.gz bench@192.168.50.1:~/
```

then:

```bash
tar xzf rxn-bench-backend-offline-*.tar.gz
cd rxn-bench-backend-offline-*/rxnbench/backend
./scripts/install_offline.sh --devices gantry,ph,camera
```

One command does all of the following:

1. Installs `uv` from the bundle's vendored binary.
2. Installs each selected device into its own standalone venv from the
   bundle's wheelhouse (no PyPI/network access used).
3. Runs that device's driver setup if it has one - today, only the pH sensor
   does (`raspi-config nonint do_i2c 0` to enable I2C, then an `i2cdetect`
   sanity scan for the EZO-pH circuit at `0x63`). The camera has no driver
   setup step - it only needs network access to Crowsnest (see
   [devices/camera/capability/backend/README.md](../devices/camera/capability/backend/README.md)).
4. Installs a systemd unit per device (`Restart=on-failure`, `RestartSec=5`,
   `WantedBy=multi-user.target`) and starts it - survives crashes and
   reboots.
5. Opens firewall ports if `ufw` is active.

Only setting up one bench device? `--devices gantry`, `--devices ph`, or
`--devices camera` installs just that one.

## Verify

```bash
sudo systemctl status rxn-bench-gantry rxn-bench-ph rxn-bench-camera
journalctl -u rxn-bench-gantry -f
```

Note: `make start-<device>`/`uv run rxn-bench-<device>` are shared-dev-workspace
commands (see [usage.md](usage.md)) - `uv run` resyncs dev-only deps like `pytest` by
default, which needs network this Pi doesn't have. Manage the installed services with
`systemctl`/`journalctl` instead.

From another machine on the same network, the frontend's server browser
should discover all of them over mDNS automatically; if mDNS is blocked (VPN,
managed network, different subnet), use its "connect manually" option with
the Pi's IP and the port from the table above.

## Discovery on the isolated bench network

The `rxnbenchpi` instrument network is intentionally **gatewayless** (no
default route — see `docs/rxnbenchpi.md`). That breaks the SiLA CDK's
zero-config mDNS discovery two independent ways. **`install_offline.sh` fixes
both automatically** (see below); this section explains what it does and how to
do it by hand if you ever need to.

- **Servers advertise `127.0.0.1`.** With the default `hostname: "0.0.0.0"`,
  the CDK auto-detects the advertise IP and falls back to loopback here (the
  Pi's hostname resolves to `127.0.1.1` in `/etc/hosts`, and its outward-IP
  probe `connect(("8.8.8.8", 80))` can't run without a default route). Clients
  then discover each server but try to connect to their *own* loopback and
  drop it. Fix: set `sila_server.hostname` to the Pi's bench IP — that fixes
  the advertised address *and* binds gRPC to that interface. The installer
  writes this into a `~/.rxn_bench/<device>.json` override per device.
- **Multicast never leaves the Pi.** The CDK announces over mDNS with a plain
  `sendto(224.0.0.251, …)` and lets the kernel's default-route lookup pick the
  egress interface. With no default route that lookup fails (`Network is
  unreachable`) and every announcement is dropped silently. **Note:** the CDK
  *ignores* `discovery.network_interfaces` — its connector passes the discovery
  config only as an on/off gate and never forwards it to the multicast socket,
  so `IP_MULTICAST_IF` is never set and that config key is a no-op. The only
  lever is an explicit route. Fix: an on-link `224.0.0.0/4` route on the bench
  interface. The installer adds a boot-time `rxn-bench-mcast-route.service`
  (a systemd oneshot running `ip route replace 224.0.0.0/4 dev <iface>`) so it
  survives reboots.

### The installer does this for you

`install_offline.sh` auto-detects the host's primary IPv4 (`hostname -I`), pins
it into each device's `~/.rxn_bench/<device>.json`, and — if the multicast group
isn't already routable — installs the route service. Override the detected IP
with `--advertise-ip <IP>`, or skip pinning entirely with `--no-pin` (correct on
a normal LAN with a default route, where neither problem exists).

### Doing it by hand

The advertise-IP override — checked ahead of the bundled `configs/<device>.json`
by each device's launcher, and it survives re-running the installer / redeploying
a new bundle:

```bash
mkdir -p ~/.rxn_bench
for dev in gantry ph_sensor camera; do
  src=$(ls ~/rxn-bench-backend-offline-*/devices/*/capability/backend/configs/${dev}.json | head -1)
  python3 - "$src" ~/.rxn_bench/${dev}.json <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
cfg = json.load(open(src))
cfg["sila_server"]["hostname"] = "192.168.50.1"
json.dump(cfg, open(dst, "w"), indent=2)
PY
done
sudo systemctl restart rxn-bench-gantry rxn-bench-ph rxn-bench-camera
```

The multicast route (apply now + persist for reboot via NetworkManager, without
bouncing the connection — `"Wired connection 1"` is the eth0 profile on the
reference Pi):

```bash
sudo ip route replace 224.0.0.0/4 dev eth0
sudo nmcli connection modify "Wired connection 1" +ipv4.routes "224.0.0.0/4 0.0.0.0"
```

Verify from an operator machine on the bench switch:

```bash
avahi-browse -r -t _sila._tcp        # each server's address should be 192.168.50.1, not 127.0.0.1
```

(`192.168.50.1` is the Pi's static bench-switch address and never changes —
it's the DHCP server/gateway for that segment. If you deploy on a *different*
IP, substitute it above.)

## Update a service later

Re-run the installer for just that device - it rebuilds only that device's
venv and restarts only that service:

```bash
./scripts/install_offline.sh --devices gantry
```

(Or, if working from a plain git checkout with network access rather than an
offline bundle, `scripts/install_service.sh gantry` does the same thing
directly - see [usage.md](usage.md).)

## Adding a new device to this flow

Nothing in `install_offline.sh` or `build_offline_bundle.sh` needs to change
structurally - add one line to the device registry in
`scripts/install_service.sh`, add a driver-setup hook at
`devices/<name>/driver/backend/install/setup_drivers.sh` if the device needs one,
and pick the next port in the registry table above.
