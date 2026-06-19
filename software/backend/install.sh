#!/bin/bash
set -e

echo "=== Automated Chem Bench - Installer ==="
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

# Move into the project directory (works regardless of where the script is called from)
cd "$(dirname "$0")"

echo ""
echo "Installing dependencies..."
uv sync

echo ""
echo "Installing chem-bench package..."
uv pip install -e .

# On Raspberry Pi, also install I2C support for the pH sensor
if [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "armv7l" ]]; then
    echo ""
    echo "Raspberry Pi detected - installing I2C dependencies..."
    uv pip install -e ".[rpi]"
fi

echo ""
echo "=== Install complete ==="
echo ""
echo "To start the SiLA server run:"
echo "  cd $(pwd)"
echo "  uv run chem-bench"
echo ""
echo "Or use the Makefile shortcut:  make start"
