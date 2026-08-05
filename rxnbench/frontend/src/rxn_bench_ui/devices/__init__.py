"""
Device plugin package.

Devices are discovered two ways, merged into one list:

1. Entry points - installed packages that declare a "rxn_bench.devices" entry
   point (see e.g. devices/gantry/frontend/pyproject.toml). This is how the
   first-party devices (gantry, ph_sensor, camera, dosing_pump,
   device_template) ship: each is its own pip-installable package (and its
   own git repo, wired into this checkout as a submodule), depended on by
   rxn-bench-ui and installed editable via `uv sync`.
2. Directory scan - a devices/<name>/frontend/__init__.py found directly
   under a devices/ directory (repo root in a source checkout, next to the
   executable in a PyInstaller build) is loaded as rxn_bench_ui.devices.<name>
   so its relative imports resolve normally. This stays as a zero-rebuild
   drop-in path for devices that aren't packaged as a formal dependency yet
   (e.g. a community/experimental device dropped into a deployed install).

A device found via entry points is a normal top-level import (its own
package name), so it does not also need to exist under devices/ on disk -
the two mechanisms don't collide because a migrated device's package no
longer has a directory.py-style devices/<name>/frontend/__init__.py (its
code lives under devices/<name>/frontend/src/<pkg>/ instead).

Each device frontend package must export:
  FEATURE_FRAGMENTS: list[str]
  create_widget(server, theme: dict) -> QWidget
"""
import importlib.metadata
import importlib.util
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _DEVICES_DIR = Path(sys.executable).resolve().parent / "devices"
else:
    # rxnbench/frontend/src/rxn_bench_ui/devices/__init__.py -> repo root is 5 levels up.
    _REPO_ROOT = Path(__file__).resolve().parents[5]
    _DEVICES_DIR = _REPO_ROOT / "devices"


def _load_device_module(name: str, frontend_dir: Path):
    module_name = f"{__name__}.{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(
        module_name,
        frontend_dir / "__init__.py",
        submodule_search_locations=[str(frontend_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    setattr(sys.modules[__name__], name, module)
    spec.loader.exec_module(module)
    return module


def _scanned_devices():
    """Devices found by scanning devices/<name>/frontend/__init__.py directly."""
    if not _DEVICES_DIR.is_dir():
        return []
    return [
        _load_device_module(entry.name, entry / "frontend")
        for entry in sorted(_DEVICES_DIR.iterdir())
        if (entry / "frontend" / "__init__.py").is_file()
    ]


def _entry_point_devices():
    """Devices found via the "rxn_bench.devices" entry-point group."""
    eps = sorted(
        importlib.metadata.entry_points(group="rxn_bench.devices"), key=lambda ep: ep.name
    )
    return [ep.load() for ep in eps]


def all_devices():
    """Return a list of all device frontend plugin modules: entry-point installed
    devices plus anything found by scanning devices/<name>/frontend/."""
    return _entry_point_devices() + _scanned_devices()
