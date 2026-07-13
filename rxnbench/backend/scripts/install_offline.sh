#!/bin/bash
# One-command backend installer: installs uv (if needed), installs the
# selected device services into their own venvs + systemd units (via
# install_service.sh), runs each device's driver setup, and opens firewall
# ports for discovery/SiLA traffic. Safe to re-run.
#
# Works two ways:
#   - Offline (recommended): run this from inside an extracted offline
#     bundle - see scripts/build_offline_bundle.sh - which ships a vendored
#     uv binary and a wheelhouse/ of pre-downloaded wheels next to this
#     script's repo root. No network is used at all in this mode.
#   - Online: run straight from a git checkout with no bundle present; falls
#     back to installing uv and dependencies from the network, same as the
#     old install.sh + install_service.sh two-step flow.
#
# Usage:
#   scripts/install_offline.sh                       # install every registered device
#   scripts/install_offline.sh --devices gantry,ph   # install just these
#   scripts/install_offline.sh --advertise-ip 192.168.50.1   # pin a specific IP
#   scripts/install_offline.sh --no-pin              # skip IP pinning entirely
#
# By default this auto-detects the host's primary IPv4 (the Pi's bench-switch
# address) and pins each device's SiLA server to it, so mDNS discovery works
# on the gatewayless bench network (where the CDK would otherwise advertise
# 127.0.0.1 and multicast couldn't egress - see docs/deployment.md). Pass
# --advertise-ip to override the detected address, or --no-pin to leave the
# CDK's 0.0.0.0 auto-detect in place (fine on a normal LAN with a default route).
#
# Device keys must match the registry in install_service.sh (this script's
# firewall-port lookup below is kept in sync with that same registry - add a
# device to both when adding a new one).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
WHEELHOUSE="${REPO_ROOT}/wheelhouse"
VENDORED_UV="${REPO_ROOT}/bin/uv"

# key:package_dir - keep in sync with _DEVICE_REGISTRY in install_service.sh.
_PACKAGE_DIR_OF() {
    case "$1" in
        gantry) echo "gantry" ;;
        ph)     echo "ph_sensor" ;;
        camera) echo "camera" ;;
        *)      return 1 ;;
    esac
}

DEVICES="gantry,ph,camera"
ADVERTISE_IP=""
NO_PIN=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --devices)
            DEVICES="$2"
            shift 2
            ;;
        --advertise-ip)
            ADVERTISE_IP="$2"
            shift 2
            ;;
        --no-pin)
            NO_PIN=1
            shift
            ;;
        *)
            echo "Usage: $0 [--devices gantry,ph] [--advertise-ip <IP> | --no-pin]"
            exit 1
            ;;
    esac
done
IFS=',' read -ra DEVICE_LIST <<< "$DEVICES"

echo "=== Rxn Bench Backend - Offline Installer ==="
echo "Devices: ${DEVICES}"
echo ""

# --- Step 1: uv ---
if [[ -x "$VENDORED_UV" ]]; then
    echo "Installing uv from the bundled binary (offline)..."
    mkdir -p "$HOME/.local/bin"
    cp "$VENDORED_UV" "$HOME/.local/bin/uv"
    chmod +x "$HOME/.local/bin/uv"
    export PATH="$HOME/.local/bin:$PATH"

    # The export above only reaches this script's own process tree - it
    # can't change PATH in the shell that invoked us (no script run as
    # `./install_offline.sh` can). Persist it for every future shell too
    # (idempotent - the grep also matches Debian/Raspberry Pi OS's default
    # ~/.bashrc, which already conditionally adds ~/.local/bin, so this is a
    # no-op there), and flag that *this* shell still needs a nudge.
    SHELL_RC="$HOME/.bashrc"
    if [[ -f "$SHELL_RC" ]] && ! grep -qF '.local/bin' "$SHELL_RC"; then
        printf '\n# Added by rxn-bench install_offline.sh\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$SHELL_RC"
    fi
    UV_PATH_NEEDS_RELOAD=1
elif command -v uv &>/dev/null; then
    echo "uv already installed: $(uv --version)"
else
    echo "No bundled uv binary found and uv isn't installed - fetching it over the network..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# --- Step 2: install the selected device services (venv + systemd + drivers) ---
OFFLINE_ARGS=()
if [[ -d "$WHEELHOUSE" ]]; then
    echo "Found bundled wheelhouse at $WHEELHOUSE - installing fully offline."
    OFFLINE_ARGS=(--offline "$WHEELHOUSE")
else
    echo "No bundled wheelhouse found at $WHEELHOUSE - installing from the network."
fi

# --- Step 2b: resolve the IP to advertise/bind (see docs/deployment.md) ---
# Auto-detect the primary IPv4 unless the user gave one or opted out. On the
# reference Pi the isolated bench interface (eth0, 192.168.50.1) is the only
# one with a global address, so `hostname -I`'s first token is it.
PIN_ARGS=()
if [[ -z "$NO_PIN" ]]; then
    if [[ -z "$ADVERTISE_IP" ]]; then
        ADVERTISE_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    fi
    if [[ "$ADVERTISE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Pinning SiLA servers to ${ADVERTISE_IP} for reliable mDNS discovery"
        echo "(override with --advertise-ip <IP>, or skip with --no-pin)."
        PIN_ARGS=(--advertise-ip "$ADVERTISE_IP")
    else
        echo "Warning: could not auto-detect a bench IP to pin (got '${ADVERTISE_IP:-none}')."
        echo "Discovery may fail on a gatewayless network - see docs/deployment.md."
        echo "Re-run with --advertise-ip <the Pi's bench IP> if so."
    fi
fi

"${SCRIPT_DIR}/install_service.sh" "${DEVICE_LIST[@]}" "${OFFLINE_ARGS[@]}" "${PIN_ARGS[@]}"

# --- Step 2c: multicast route for mDNS discovery on a gatewayless network ---
# The SiLA CDK announces to 224.0.0.251 with a plain sendto() and relies on the
# kernel's default-route lookup to choose an egress interface. The isolated
# bench network has no default route by design, so that lookup fails and every
# announcement is dropped - discovery silently fails even with everything else
# correct. The CDK's connector never forwards discovery.network_interfaces to
# its multicast socket (it uses the config only as an on/off gate), so
# IP_MULTICAST_IF is never set and a route is the only lever. Install a tiny
# boot-time oneshot that pins an on-link 224.0.0.0/4 route on the bench
# interface. Gated on the multicast group not already being routable, so it's a
# no-op on a normal LAN where a default (or existing multicast) route exists.
if [[ -n "$ADVERTISE_IP" ]] && [[ "$ADVERTISE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        && ! ip route get 224.0.0.251 &>/dev/null; then
    MCAST_IFACE="$(ip -o -4 addr show | awk -v ip="$ADVERTISE_IP" '$4 ~ "^"ip"/" {print $2; exit}')"
    IP_BIN="$(command -v ip)"
    if [[ -n "$MCAST_IFACE" && -n "$IP_BIN" ]]; then
        echo ""
        echo "Multicast isn't routable (gatewayless network) - installing a boot-time"
        echo "224.0.0.0/4 route on ${MCAST_IFACE} so mDNS discovery works..."
        sudo tee /etc/systemd/system/rxn-bench-mcast-route.service > /dev/null <<EOF
[Unit]
Description=Rxn Bench multicast route for SiLA/mDNS discovery
Wants=network-online.target
After=network-online.target
Before=rxn-bench-gantry.service rxn-bench-ph.service rxn-bench-camera.service

[Service]
Type=oneshot
ExecStart=${IP_BIN} route replace 224.0.0.0/4 dev ${MCAST_IFACE}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable rxn-bench-mcast-route.service
        sudo systemctl restart rxn-bench-mcast-route.service
        echo "Installed rxn-bench-mcast-route.service (224.0.0.0/4 dev ${MCAST_IFACE})."
    else
        echo ""
        echo "Warning: multicast isn't routable and no interface owns ${ADVERTISE_IP}."
        echo "mDNS discovery will fail - add a 224.0.0.0/4 route manually (see docs/deployment.md)."
    fi
fi

# --- Step 3: firewall (only touch it if ufw is present and active - most
#     bench Pis don't run one, but this keeps the installer correct if IT does) ---
if command -v ufw &>/dev/null && sudo ufw status | grep -q "Status: active"; then
    echo ""
    echo "ufw is active - opening ports for the selected services..."
    for key in "${DEVICE_LIST[@]}"; do
        pkg_dir="$(_PACKAGE_DIR_OF "$key")" || continue
        cfg="$(ls "${REPO_ROOT}/devices/${pkg_dir}/backend/configs/"*.json 2>/dev/null | head -1)"
        [[ -z "$cfg" ]] && continue
        port="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['sila_server']['port'])" "$cfg")"
        sudo ufw allow "${port}/tcp" comment "rxn-bench-${key} (SiLA)"
    done
    sudo ufw allow 5353/udp comment "rxn-bench mDNS discovery"
fi

echo ""
echo "=== Install complete ==="
echo ""
echo "Installed and started: ${DEVICES}"
echo "Check status any time with: sudo systemctl status rxn-bench-<gantry|ph>"
echo "View logs with:              journalctl -u rxn-bench-<gantry|ph> -f"

if [[ -n "${UV_PATH_NEEDS_RELOAD:-}" ]]; then
    echo ""
    echo "uv was installed to ~/.local/bin, which isn't on PATH in *this* shell yet"
    echo "(new shells will pick it up automatically). Run 'source ~/.bashrc' or open"
    echo "a new terminal before using 'uv'/'make start-<device>' directly here."
fi
