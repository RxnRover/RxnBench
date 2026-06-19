#!/bin/bash
set -e

echo "=== Chem Bench UI - Installer ==="
echo ""

if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
else
    echo "uv already installed: $(uv --version)"
fi

cd "$(dirname "$0")"

echo ""
echo "Installing dependencies..."
uv sync

echo ""
echo "Installing chem-bench-ui package..."
uv pip install -e .

echo ""
echo "=== Install complete ==="
echo ""
echo "To launch the UI:"
echo "  cd $(pwd)"
echo "  uv run chem-bench-ui"
