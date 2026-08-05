#!/usr/bin/env python3
"""
aggregate_toolheads.py - copy each device driver's toolhead config into the
gantry capability package's bundled toolheads/ directory.

Toolhead configs (e.g. the pH probe's mount geometry/engage-depth YAML) live
with the device driver that owns the physical toolhead (devices/<name>/driver/
toolhead/<name>_toolhead.yaml), not with gantry - gantry doesn't know what a
pH probe is, it just mounts whatever toolhead config is handed to it. But
rxn_bench_gantry.toolhead_config.ToolheadConfig.load() reads from a single
bundled directory (rxn_bench_gantry/toolheads/<name>/<name>_toolhead.yaml), so
this deploy-time step aggregates every registered device's toolhead config
into that directory before the gantry capability package is installed/run.

Safe to re-run: it only ever copies (overwrites), never deletes a toolhead
folder that no longer has a source (so a manually-added toolhead isn't
clobbered by omission).

Run from rxnbench/backend/: python scripts/aggregate_toolheads.py
"""
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEVICES_DIR = _REPO_ROOT / "devices"
_GANTRY_TOOLHEADS_DIR = (
    _DEVICES_DIR / "gantry" / "capability" / "backend"
    / "src" / "rxn_bench_gantry" / "toolheads"
)


def main() -> None:
    if not _GANTRY_TOOLHEADS_DIR.is_dir():
        sys.exit(f"error: {_GANTRY_TOOLHEADS_DIR} not found (gantry capability package missing?)")

    copied = 0
    for driver_toolhead_dir in sorted(_DEVICES_DIR.glob("*/driver/toolhead")):
        for yaml_file in sorted(driver_toolhead_dir.glob("*_toolhead.yaml")):
            name = yaml_file.stem.removesuffix("_toolhead")
            out_dir = _GANTRY_TOOLHEADS_DIR / name
            out_dir.mkdir(exist_ok=True)
            shutil.copy2(yaml_file, out_dir / yaml_file.name)
            print(f"aggregated {yaml_file.relative_to(_REPO_ROOT)} -> "
                  f"{(out_dir / yaml_file.name).relative_to(_REPO_ROOT)}")
            copied += 1

    if copied == 0:
        print("no device-driver toolhead configs found to aggregate.")


if __name__ == "__main__":
    main()
