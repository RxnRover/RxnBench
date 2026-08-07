"""
Camera frontend plugin.

Declares FEATURE_FRAGMENTS matched against SiLA feature identifiers and
provides create_widget() for the app shell's device registry. This is the
same contract every device frontend plugin exports - see
devices/gantry/capability/frontend/__init__.py or devices/ph_sensor/capability/frontend/__init__.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from rxn_bench_ui.discovery import DiscoveredServer

FEATURE_FRAGMENTS: list[str] = [
    "Camera",
]


def create_widget(server: "DiscoveredServer", theme: dict) -> "QWidget":
    """Instantiate and return a CameraWidget for the given server."""
    from .widget import CameraWidget
    return CameraWidget(server, theme)
