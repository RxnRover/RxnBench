#!/usr/bin/env python3
"""
copy_device_plugins.py - stage devices/<name>/frontend/ next to a built exe.

rxn_bench_ui/devices/__init__.py discovers device plugins from a devices/
folder beside the executable when frozen (see that file's docstring). This
script populates that folder from the repo's devices/<name>/frontend/ dirs so
a fresh build ships with the same devices it has today - backend/ and
__pycache__ are left out since the frontend never bundles backend code.

Run from rxnbench/frontend/: python packaging/copy_device_plugins.py "dist/Rxn Bench"
"""
import shutil
import sys
from pathlib import Path

_REPO_DEVICES_DIR = Path(__file__).resolve().parents[3] / "devices"
_IGNORE = shutil.ignore_patterns("backend", "__pycache__", "*.pyc")


def main():
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <dist-dir-containing-the-exe>")
    dist_dir = Path(sys.argv[1]).resolve()
    if not dist_dir.is_dir():
        sys.exit(f"error: {dist_dir} is not a directory (build the app first)")

    out_devices_dir = dist_dir / "devices"
    if out_devices_dir.exists():
        shutil.rmtree(out_devices_dir)
    out_devices_dir.mkdir()

    for entry in sorted(_REPO_DEVICES_DIR.iterdir()):
        frontend_dir = entry / "frontend"
        if not (frontend_dir / "__init__.py").is_file():
            continue
        shutil.copytree(frontend_dir, out_devices_dir / entry.name / "frontend", ignore=_IGNORE)
        print(f"staged {entry.name}/frontend -> {out_devices_dir / entry.name / 'frontend'}")


if __name__ == "__main__":
    main()
