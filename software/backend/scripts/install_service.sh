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
#
# To add a new device: add one line to _DEVICE_REGISTRY below. Nothing else
# in this script needs to change.

set -e

# key:package_dir:bin_name:description:arm_only_extra (last field may be empty)
_DEVICE_REGISTRY=(
    "gantry:gantry:rxn-bench-gantry:Rxn Bench Gantry SiLA server:"
    "ph:ph_sensor:rxn-bench-ph:Rxn Bench pH Sensor SiLA server:rpi"
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

# --- Parse args: device keys / --all, plus an optional --offline flag ---
DEVICE_KEYS=()
OFFLINE_WHEELHOUSE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --offline)
            OFFLINE_WHEELHOUSE="$2"
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

    echo ""
    echo "Installing systemd service: $SERVICE_NAME"
    echo "  Working dir : $WORKING_DIR"
    echo "  Venv        : $VENV_DIR"
    echo "  Running as  : $RUN_USER"
    echo ""

    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=${DESCRIPTION}
After=network.target

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
