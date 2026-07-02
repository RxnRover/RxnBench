#!/bin/bash
set -e

echo "=== Rxn Bench Backend - Installer ==="
echo ""

# Install uv if not already present
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for the rest of this script
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
else
    echo "uv already installed: $(uv --version)"
fi

# Move into the backend workspace directory (works regardless of where the script is called from)
cd "$(dirname "$0")"

echo ""
echo "Installing workspace dependencies (gantry, ph_sensor, client, device_template)..."
uv sync

# On Raspberry Pi, also install I2C support for the pH sensor
if [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "armv7l" ]]; then
    echo ""
    echo "Raspberry Pi detected - installing pH sensor I2C dependencies..."
    uv sync --package rxn-bench-ph --extra rpi
fi

echo ""
echo "=== Install complete ==="
echo ""
echo "The gantry and pH sensor now run as two independent SiLA2 servers."
echo ""
echo "To start both with mock hardware (no Pi/SV08/sensor needed):"
echo "  make start-mock"
echo ""
echo "To start against real hardware:"
echo "  make start-gantry   # or: cd gantry && uv run rxn-bench-gantry"
echo "  make start-ph       # or: cd ph_sensor && uv run rxn-bench-ph"
echo ""
echo "To run a server as a systemd service that starts on boot:"
echo "  scripts/install_service.sh gantry"
echo "  scripts/install_service.sh ph"
