#!/bin/bash
# Installs the chem-bench SiLA server as a systemd service so it
# starts automatically on boot. Run once after install.sh.

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER="$(whoami)"
UV_BIN="$(which uv)"
SERVICE_NAME="chem-bench"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Installing systemd service for chem-bench..."
echo "  Project dir : $PROJECT_DIR"
echo "  Running as  : $USER"
echo ""

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Automated Chem Bench SiLA Server
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${UV_BIN} run connector start --app chem_bench.__main__:create_app --config-path config.json
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo ""
echo "Service installed and started."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME   - check if running"
echo "  sudo systemctl stop $SERVICE_NAME     - stop the server"
echo "  sudo systemctl restart $SERVICE_NAME  - restart after code changes"
echo "  journalctl -u $SERVICE_NAME -f        - view live logs"
