#!/bin/bash
# Driver setup for rxn-bench-ph: enables the I2C interface the Atlas
# Scientific EZO-pH circuit talks over. Called automatically by
# software/backend/scripts/install_offline.sh (and install_service.sh) when
# installing the ph_sensor service - safe to re-run.
set -e

if [[ "$(uname -m)" != "aarch64" && "$(uname -m)" != "armv7l" ]]; then
    echo "  (not running on a Raspberry Pi - skipping I2C setup)"
    exit 0
fi

if ! command -v raspi-config &>/dev/null; then
    echo "  raspi-config not found - enable I2C manually (Interface Options -> I2C) and re-run."
    exit 0
fi

echo "  Enabling I2C interface..."
sudo raspi-config nonint do_i2c 0

if command -v i2cdetect &>/dev/null; then
    echo "  Scanning I2C bus 1 for devices (expect the EZO-pH circuit at 0x63):"
    i2cdetect -y 1 || echo "  (i2cdetect failed - the i2c-dev kernel module may need a reboot to load)"
else
    echo "  i2c-tools not installed - install it to verify wiring with 'i2cdetect -y 1'."
fi
