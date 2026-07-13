"""
Device plugin package.

Auto-discovers every device under a devices/ directory (each device is a
self-contained devices/<name>/{backend,frontend} folder - see
docs/ai/CURRENT_STATE.md). A device is recognized if devices/<name>/frontend/
exists; its __init__.py is loaded as rxn_bench_ui.devices.<name> so its
relative imports (e.g. `from ...discovery import ...`) resolve normally.

In a source checkout, devices/ is the repo-root folder five levels up from
this file. In a packaged (PyInstaller) build there is no repo checkout, so
devices/ is instead expected to sit next to the executable - this keeps the
same drop-in plugin model after packaging: adding device support to a
deployed install means adding a devices/<name>/frontend/ folder there, no
rebuild required.

Each device frontend package must export:
  FEATURE_FRAGMENTS: list[str]
  create_widget(server, theme: dict) -> QWidget
"""
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


def all_devices():
    """Return a list of all device frontend plugin modules, one per devices/<name>/frontend/."""
    if not _DEVICES_DIR.is_dir():
        return []
    return [
        _load_device_module(entry.name, entry / "frontend")
        for entry in sorted(_DEVICES_DIR.iterdir())
        if (entry / "frontend" / "__init__.py").is_file()
    ]
