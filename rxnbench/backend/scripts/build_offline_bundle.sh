#!/bin/bash
# Builds a fully offline install bundle for the Rxn Bench backend, targeting
# a Raspberry Pi (aarch64, Python 3.13 by default).
#
# Run this on a dev machine WITH internet access. The output tarball needs
# no network at all to install - copy it to the Pi (USB drive/scp) and run
# install_offline.sh from inside it. See docs/deployment.md.
#
# Usage:
#   scripts/build_offline_bundle.sh [output_dir]
#
# Override target platform if needed:
#   PYTHON_VERSION=310 PLATFORM_TAG=linux_aarch64 PIP_PLATFORM_TAG=manylinux2014_aarch64 scripts/build_offline_bundle.sh
#
# PLATFORM_TAG only labels the output bundle/directory name; PIP_PLATFORM_TAG
# is the actual tag `pip download --platform` matches wheels against. They
# differ because compiled wheels (grpcio, lxml, pydantic-core, ...) are
# published under manylinux* tags, not the bare "linux_aarch64"/"linux_x86_64"
# family - passing the bare tag to pip silently only matches pure-Python
# wheels and 404s on every compiled one.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/../.." && pwd)"
OUT_DIR="${1:-${REPO_ROOT}/rxnbench/backend/dist}"

PYTHON_VERSION="${PYTHON_VERSION:-313}"     # matches the Pi's Raspberry Pi OS Python.
PLATFORM_TAG="${PLATFORM_TAG:-linux_aarch64}"
PIP_PLATFORM_TAG="${PIP_PLATFORM_TAG:-manylinux2014_aarch64}"
UV_TARGET="${UV_TARGET:-aarch64-unknown-linux-gnu}"
UV_VERSION="${UV_VERSION:-$(uv --version | awk '{print $2}')}"

PIWHEELS_INDEX="https://www.piwheels.org/simple"
UNITELABS_INDEX="https://gitlab.com/api/v4/groups/1009252/-/packages/pypi/simple"

VERSION="$(date +%Y%m%d)"
BUNDLE_NAME="rxn-bench-backend-offline-${VERSION}-${PLATFORM_TAG}"
STAGE_DIR="${OUT_DIR}/${BUNDLE_NAME}"

echo "=== Building offline backend bundle ==="
echo "  Target      : ${PLATFORM_TAG}, CPython ${PYTHON_VERSION}"
echo "  uv          : ${UV_VERSION} (${UV_TARGET})"
echo "  Output      : ${STAGE_DIR}.tar.gz"
echo ""

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/wheelhouse" "$STAGE_DIR/bin"

# --- 1. Export locked requirements for every installable device + client ---
# Each device package itself is installed later via editable install from the
# source tree already in the bundle (step 4 + install_service.sh) - only its
# *dependencies* need to come from the wheelhouse, so the "-e <local path>"
# line uv export emits for the workspace member itself is filtered out below.
cd "$BACKEND_DIR"
REQS_DIR="$(mktemp -d)"
uv export --package rxn-bench-gantry --format requirements-txt --no-header --no-annotate --no-hashes > "${REQS_DIR}/gantry.txt"
uv export --package rxn-bench-ph --extra rpi --format requirements-txt --no-header --no-annotate --no-hashes > "${REQS_DIR}/ph.txt"
uv export --package rxn-bench-camera --format requirements-txt --no-header --no-annotate --no-hashes > "${REQS_DIR}/camera.txt"
uv export --package rxn-bench-dosing-pump --extra rpi --format requirements-txt --no-header --no-annotate --no-hashes > "${REQS_DIR}/dosing_pump.txt"
uv export --package rxn-bench-client --format requirements-txt --no-header --no-annotate --no-hashes > "${REQS_DIR}/client.txt"
grep -h -v '^-e ' "${REQS_DIR}"/*.txt | sort -u > "${REQS_DIR}/merged.txt"

# install_service.sh installs each device with `uv pip install --no-index -e
# <device>`, which builds the package locally using its build backend
# (hatchling, per every device's [build-system]) plus hatchling's own
# editable-build helper (editables) - neither is a *runtime* dependency, so
# `uv export` above never lists them, but the offline `--no-index` install
# has nowhere else to get them from. Add them explicitly.
printf 'hatchling\neditables\n' >> "${REQS_DIR}/merged.txt"

# --- 2. Download every wheel for the target platform (no compiling on the Pi) ---
echo "Downloading wheels for ${PIP_PLATFORM_TAG}/cp${PYTHON_VERSION} into wheelhouse/..."
pip download \
    -r "${REQS_DIR}/merged.txt" \
    --dest "${STAGE_DIR}/wheelhouse" \
    --platform "${PIP_PLATFORM_TAG}" \
    --python-version "${PYTHON_VERSION}" \
    --implementation cp \
    --abi "cp${PYTHON_VERSION}" \
    --only-binary=:all: \
    --index-url "https://pypi.org/simple" \
    --extra-index-url "${PIWHEELS_INDEX}" \
    --extra-index-url "${UNITELABS_INDEX}"
rm -rf "$REQS_DIR"

# --- 3. Vendor a matching uv binary so the Pi needs no network for uv itself ---
echo "Downloading uv ${UV_VERSION} (${UV_TARGET})..."
UV_TARBALL="uv-${UV_TARGET}.tar.gz"
curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_TARBALL}" -o "/tmp/${UV_TARBALL}"
tar -xzf "/tmp/${UV_TARBALL}" -C /tmp
cp "/tmp/uv-${UV_TARGET}/uv" "${STAGE_DIR}/bin/uv"
chmod +x "${STAGE_DIR}/bin/uv"
rm -rf "/tmp/${UV_TARBALL}" "/tmp/uv-${UV_TARGET}"

# --- 4. Copy the repo source needed to install + run (skip dev-only cruft) ---
echo "Copying repo source (devices/, rxnbench/backend/)..."
tar -C "$REPO_ROOT" \
    --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
    --exclude='.mypy_cache' --exclude='*.pyc' --exclude='logs/*.jsonl' \
    --exclude='devices/*/frontend' --exclude='rxnbench/backend/dist' \
    -cf - devices rxnbench/backend \
    | tar -C "$STAGE_DIR" -xf -

# --- 5. Package it up ---
cd "$OUT_DIR"
tar -czf "${BUNDLE_NAME}.tar.gz" "$BUNDLE_NAME"
rm -rf "$STAGE_DIR"

echo ""
echo "=== Bundle built: ${OUT_DIR}/${BUNDLE_NAME}.tar.gz ==="
echo ""
echo "Copy it to the Pi (USB drive/scp), then on the Pi:"
echo "  tar xzf ${BUNDLE_NAME}.tar.gz"
echo "  cd ${BUNDLE_NAME}/rxnbench/backend"
echo "  ./scripts/install_offline.sh --devices gantry,ph,camera,pump"
