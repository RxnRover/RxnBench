#!/bin/bash
# Installs one or more rxn-bench backend services as systemd units so they
# start automatically on boot, each in its own standalone venv (separate from
# the shared dev workspace venv) so services can be updated/redeployed
# independently in production.
#
# Safe to re-run for an already-installed service: it refreshes that
# service's venv and restarts it, without touching other services.
#
# Usage:
#   scripts/install_service.sh gantry
#   scripts/install_service.sh ph
#   scripts/install_service.sh gantry ph              # install several
#   scripts/install_service.sh --all                  # install every registered device
#   scripts/install_service.sh ph --offline /path/to/wheelhouse
#   scripts/install_service.sh --all --advertise-ip 192.168.50.1
#
# --advertise-ip <IP> pins each device's SiLA server to that IP via a
# ~/.rxn_bench/<device>.json override: it sets sila_server.hostname (the
# address advertised over mDNS and bound by gRPC) and discovery.network_interfaces
# (IP_MULTICAST_IF). This is required for discovery to work on the gatewayless
# bench network, where the CDK's auto-detect otherwise advertises 127.0.0.1 and
# multicast can't egress - see docs/deployment.md. install_offline.sh passes
# this automatically; omit it on a normal LAN with a default route.
#
# To add a new device: add one line to _DEVICE_REGISTRY below. Nothing else
# in this script needs to change.

set -e

# key:package_dir:bin_name:description:arm_only_extra (last field may be empty)
_DEVICE_REGISTRY=(
    "gantry:gantry:rxn-bench-gantry:Rxn Bench Gantry SiLA server:"
    "ph:ph_sensor:rxn-bench-ph:Rxn Bench pH Sensor SiLA server:rpi"
    "camera:camera:rxn-bench-camera:Rxn Bench Camera SiLA server:"
)

_usage() {
    echo "Usage: $0 <device> [<device> ...] | --all [--offline <wheelhouse-dir>]"
    echo "  devices: $(for e in "${_DEVICE_REGISTRY[@]}"; do echo -n "${e%%:*} "; done)"
    exit 1
}

_lookup() {
    local key="$1"
    for entry in "${_DEVICE_REGISTRY[@]}"; do
        if [[ "${entry%%:*}" == "$key" ]]; then
            echo "$entry"
            return 0
        fi
    done
    return 1
}

# --- Parse args: device keys / --all, plus optional --offline / --advertise-ip flags ---
DEVICE_KEYS=()
OFFLINE_WHEELHOUSE=""
ADVERTISE_IP=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --offline)
            OFFLINE_WHEELHOUSE="$2"
            shift 2
            ;;
        --advertise-ip)
            ADVERTISE_IP="$2"
            shift 2
            ;;
        --all)
            for entry in "${_DEVICE_REGISTRY[@]}"; do
                DEVICE_KEYS+=("${entry%%:*}")
            done
            shift
            ;;
        *)
            DEVICE_KEYS+=("$1")
            shift
            ;;
    esac
done

[[ ${#DEVICE_KEYS[@]} -eq 0 ]] && _usage

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/../.." && pwd)"
RUN_USER="$(whoami)"

for KEY in "${DEVICE_KEYS[@]}"; do
    ENTRY="$(_lookup "$KEY")" || { echo "Unknown device: $KEY"; _usage; }
    IFS=':' read -r _ PACKAGE_DIR BIN_NAME DESCRIPTION ARM_EXTRA <<< "$ENTRY"

    EXTRA=""
    if [[ -n "$ARM_EXTRA" && ( "$(uname -m)" == "aarch64" || "$(uname -m)" == "armv7l" ) ]]; then
        EXTRA="[${ARM_EXTRA}]"
    fi

    WORKING_DIR="${REPO_ROOT}/devices/${PACKAGE_DIR}/backend"
    VENV_DIR="${WORKING_DIR}/.venv"
    BIN_PATH="${VENV_DIR}/bin/${BIN_NAME}"
    SERVICE_NAME="${BIN_NAME}"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

    echo "=== ${DESCRIPTION} (${KEY}) ==="
    echo "Installing standalone venv for ${PACKAGE_DIR} (independent of the shared dev workspace)..."
    uv venv --no-project "$VENV_DIR" --allow-existing

    if [[ -n "$OFFLINE_WHEELHOUSE" ]]; then
        uv pip install --python "${VENV_DIR}/bin/python" \
            --no-index --find-links "$OFFLINE_WHEELHOUSE" \
            -e "${WORKING_DIR}${EXTRA}"
    else
        uv pip install --python "${VENV_DIR}/bin/python" -e "${WORKING_DIR}${EXTRA}"
    fi

    if [[ ! -x "$BIN_PATH" ]]; then
        echo "Error: $BIN_PATH was not created by the install above."
        exit 1
    fi

    DRIVER_HOOK="${WORKING_DIR}/install/setup_drivers.sh"
    if [[ -x "$DRIVER_HOOK" ]]; then
        echo "Running driver setup for ${PACKAGE_DIR}..."
        "$DRIVER_HOOK"
    fi

    # --- Pin the advertised/bound IP for reliable mDNS discovery ---
    # Writes a ~/.rxn_bench/<device>.json override (checked ahead of the
    # bundled config by the device launcher) with sila_server.hostname set to
    # $ADVERTISE_IP - that fixes the mDNS-advertised A record (the CDK would
    # otherwise auto-detect 127.0.0.1 here) and binds gRPC to that interface.
    # We deliberately do NOT touch discovery.network_interfaces: the CDK's
    # connector never forwards it to the multicast socket, so it's a no-op -
    # multicast egress is handled by the route service in install_offline.sh,
    # not by config (see docs/deployment.md). Idempotent: patches an existing
    # override in place (preserving other edits) or seeds a new one from the
    # bundled config. Runs as the invoking user, so ~ is that user's home - the
    # same home the systemd service (User=${RUN_USER}) reads at startup.
    if [[ -n "$ADVERTISE_IP" ]]; then
        BUNDLED_CFG="${WORKING_DIR}/configs/${PACKAGE_DIR}.json"
        OVERRIDE_CFG="${HOME}/.rxn_bench/${PACKAGE_DIR}.json"
        if [[ -f "$BUNDLED_CFG" ]]; then
            mkdir -p "${HOME}/.rxn_bench"
            python3 - "$BUNDLED_CFG" "$OVERRIDE_CFG" "$ADVERTISE_IP" <<'PY'
import json, os, sys
bundled, override, ip = sys.argv[1], sys.argv[2], sys.argv[3]
src = override if os.path.exists(override) else bundled
with open(src) as f:
    cfg = json.load(f)
cfg.setdefault("sila_server", {})["hostname"] = ip
with open(override, "w") as f:
    json.dump(cfg, f, indent=2)
PY
            echo "Pinned SiLA advertise/bind IP to ${ADVERTISE_IP} (${OVERRIDE_CFG})."
        else
            echo "Warning: no bundled config at ${BUNDLED_CFG}; cannot pin advertise IP for ${KEY}."
        fi
    fi

    echo ""
    echo "Installing systemd service: $SERVICE_NAME"
    echo "  Working dir : $WORKING_DIR"
    echo "  Venv        : $VENV_DIR"
    echo "  Running as  : $RUN_USER"
    echo ""

    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=${DESCRIPTION}
# network-online (not just network.target): the server binds to a specific
# interface IP when --advertise-ip is used, so it must wait for that address
# to be configured. Restart=on-failure is still the backstop if it isn't yet.
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${WORKING_DIR}
ExecStart=${BIN_PATH}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"

    echo ""
    echo "${SERVICE_NAME} installed and (re)started."
    echo ""
done

echo "To update a service later: re-run this script for just that device"
echo "(rebuilds only its .venv and restarts its service; others are untouched)."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status <service>   - check if running"
echo "  sudo systemctl stop <service>     - stop the server"
echo "  sudo systemctl restart <service>  - restart after code changes"
echo "  journalctl -u <service> -f        - view live logs"
