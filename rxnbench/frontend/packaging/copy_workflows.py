#!/usr/bin/env python3
"""
copy_workflows.py - stage example scripts and workspace configs next to a built exe.

Mirrors copy_device_plugins.py's pattern: populates two folders beside the
executable so a fresh install ships ready-to-run starting points instead of
an operator having to find them in a source checkout.

- Scripts/     <- rxnbench/backend/client/scripts/ (the experiment workflows
                   the Experiment Runner's "Browse" dialog defaults to)
- Workspaces/  <- devices/gantry/backend/src/rxn_bench_gantry/workspace/definitions/
                   (*.yaml only). These are EXAMPLES to import and edit, not
                   live device config - the gantry backend has its own copy on
                   the Pi that it actually loads workspaces from by name.

Run from rxnbench/frontend/: python packaging/copy_workflows.py "dist/Rxn Bench"
"""
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_SRC = _REPO_ROOT / "rxnbench" / "backend" / "client" / "scripts"
_WORKSPACES_SRC = (
    _REPO_ROOT / "devices" / "gantry" / "backend" / "src" / "rxn_bench_gantry"
    / "workspace" / "definitions"
)
_IGNORE_SCRIPTS = shutil.ignore_patterns("__pycache__", "*.pyc")


def main():
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <dist-dir-containing-the-exe>")
    dist_dir = Path(sys.argv[1]).resolve()
    if not dist_dir.is_dir():
        sys.exit(f"error: {dist_dir} is not a directory (build the app first)")

    out_scripts_dir = dist_dir / "Scripts"
    if out_scripts_dir.exists():
        shutil.rmtree(out_scripts_dir)
    shutil.copytree(_SCRIPTS_SRC, out_scripts_dir, ignore=_IGNORE_SCRIPTS)
    print(f"staged {_SCRIPTS_SRC} -> {out_scripts_dir}")

    out_workspaces_dir = dist_dir / "Workspaces"
    if out_workspaces_dir.exists():
        shutil.rmtree(out_workspaces_dir)
    out_workspaces_dir.mkdir()
    for yaml_file in sorted(_WORKSPACES_SRC.glob("*.yaml")):
        shutil.copy2(yaml_file, out_workspaces_dir / yaml_file.name)
    print(f"staged {_WORKSPACES_SRC}/*.yaml -> {out_workspaces_dir}")


if __name__ == "__main__":
    main()
