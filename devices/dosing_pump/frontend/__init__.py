"""
Dosing pump device plugin.

Declares FEATURE_FRAGMENTS matched against SiLA feature identifiers and
provides create_widget() for the app shell's device registry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from ...discovery import DiscoveredServer

FEATURE_FRAGMENTS: list[str] = [
    # Rxn Bench native
    "DosingPump",
    # SiLA standard pump / dosing features
    "PumpDrive",
    "PumpFluidDosingService",
    "ContinuousFlowDosingService",
]


def create_widget(server: "DiscoveredServer", theme: dict) -> "QWidget":
    """Instantiate and return a DosingPumpWidget for the given server."""
    from .widget import DosingPumpWidget
    return DosingPumpWidget(server, theme)
