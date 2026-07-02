#!/bin/bash
# Installs one rxn-bench backend service (gantry or ph) as a systemd unit so
# it starts automatically on boot, and gives it its own standalone venv
# (separate from the shared dev workspace venv) so gantry and ph can be
# updated and redeployed independently in production.
#
# Safe to re-run for an already-installed service: it refreshes that
# service's venv and restarts it, without touching the other service.
#
# Usage:
#   scripts/install_service.sh gantry
#   scripts/install_service.sh ph

set -e

SERVICE_KEY="$1"
case "$SERVICE_KEY" in
    gantry)
        PACKAGE_DIR="gantry"
        BIN_NAME="rxn-bench-gantry"
        DESCRIPTION="Rxn Bench Gantry SiLA server"
        EXTRA=""
        ;;
    ph)
        PACKAGE_DIR="ph_sensor"
        BIN_NAME="rxn-bench-ph"
        DESCRIPTION="Rxn Bench pH Sensor SiLA server"
        # On Raspberry Pi, pull in the I2C dependencies for the real sensor driver.
        if [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "armv7l" ]]; then
            EXTRA="[rpi]"
        else
            EXTRA=""
        fi
        ;;
    *)
        echo "Usage: $0 <gantry|ph>"
        exit 1
        ;;
esac

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/../.." && pwd)"
WORKING_DIR="${REPO_ROOT}/devices/${PACKAGE_DIR}/backend"
VENV_DIR="${WORKING_DIR}/.venv"
BIN_PATH="${VENV_DIR}/bin/${BIN_NAME}"
RUN_USER="$(whoami)"
SERVICE_NAME="${BIN_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Installing standalone venv for ${PACKAGE_DIR} (independent of the shared dev workspace)..."
uv venv --no-project "$VENV_DIR" --allow-existing
uv pip install --python "${VENV_DIR}/bin/python" -e "${WORKING_DIR}${EXTRA}"

if [[ ! -x "$BIN_PATH" ]]; then
    echo "Error: $BIN_PATH was not created by the install above."
    exit 1
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
echo "Service installed and (re)started."
echo ""
echo "To update just this service later: re-run this script (rebuilds only"
echo "${PACKAGE_DIR}/.venv and restarts ${SERVICE_NAME}; the other service is untouched)."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME   - check if running"
echo "  sudo systemctl stop $SERVICE_NAME     - stop the server"
echo "  sudo systemctl restart $SERVICE_NAME  - restart after code changes"
echo "  journalctl -u $SERVICE_NAME -f        - view live logs"
