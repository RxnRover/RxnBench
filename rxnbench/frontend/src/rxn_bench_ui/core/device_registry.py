"""Device registry - calls devices.all_devices() to discover device packages dynamically."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from ..discovery import DiscoveredServer

from .. import devices as _dev_pkg


def _device_modules():
    return _dev_pkg.all_devices()


def is_recognized(server: "DiscoveredServer") -> bool:
    """Return True if any feature on this server matches any device plugin."""
    all_features = " ".join(server.features).lower()
    return any(
        frag.lower() in all_features
        for mod in _device_modules()
        for frag in mod.FEATURE_FRAGMENTS
    )


def panel_for(server: "DiscoveredServer", t: dict) -> "QWidget":
    """
    Return the most appropriate device panel for *server*.

    Iterates device plugins in discovery order, matching their FEATURE_FRAGMENTS
    against all feature identifiers the server advertises.
    Falls back to GenericDeviceWidget when no plugin matches.
    """
    from .generic_device import GenericDeviceWidget

    all_features = " ".join(server.features).lower()
    for mod in _device_modules():
        if any(frag.lower() in all_features for frag in mod.FEATURE_FRAGMENTS):
            return mod.create_widget(server, t)

    return GenericDeviceWidget(server, t)
