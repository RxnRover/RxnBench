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

# Only our own feature identifier: this widget drives the rxnbench Gantry
# feature's specific RPCs, so matching generic SiLA motion features
# (LinearMotion, XYZStage, ...) would bind it to servers it cannot talk to.
FEATURE_FRAGMENTS: list[str] = [
    "Gantry",
]


def create_widget(server: "DiscoveredServer", theme: dict) -> "QWidget":
    """Instantiate and return a GantryWidget for the given server."""
    from .widget import GantryWidget
    return GantryWidget(server, theme)
