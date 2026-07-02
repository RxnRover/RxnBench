"""
Gantry device plugin.

Declares FEATURE_FRAGMENTS matched against SiLA feature identifiers and
provides create_widget() for the app shell's device registry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from ...discovery import DiscoveredServer

FEATURE_FRAGMENTS: list[str] = [
    # Chembench native
    "Gantry",
    # SiLA standard motion / positioning
    "LinearMotion",
    "XYZStage",
    "PositioningXY",
    "AxisSystem",
]


def create_widget(server: "DiscoveredServer", theme: dict) -> "QWidget":
    """Instantiate and return a GantryWidget for the given server."""
    from .widget import GantryWidget
    return GantryWidget(server, theme)
