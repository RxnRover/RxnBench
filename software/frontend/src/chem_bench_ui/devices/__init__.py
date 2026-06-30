"""
Device plugin package.

Auto-discovers all sub-packages (one per device type).
Each sub-package must export:
  FEATURE_FRAGMENTS: list[str]
  create_widget(server, theme: dict) -> QWidget
"""
import importlib
import pkgutil


def all_devices():
    """Return a list of all device plugin modules (one per sub-package)."""
    return [
        importlib.import_module(f".{name}", package=__name__)
        for _, name, ispkg in pkgutil.iter_modules(__path__)
        if ispkg
    ]
