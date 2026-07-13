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
#   scripts/install_offline.sh                      # install every registered device
#   scripts/install_offline.sh --devices gantry,ph   # install just these
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
while [[ $# -gt 0 ]]; do
    case "$1" in
        --devices)
            DEVICES="$2"
            shift 2
            ;;
        *)
            echo "Usage: $0 [--devices gantry,ph]"
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

"${SCRIPT_DIR}/install_service.sh" "${DEVICE_LIST[@]}" "${OFFLINE_ARGS[@]}"

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
