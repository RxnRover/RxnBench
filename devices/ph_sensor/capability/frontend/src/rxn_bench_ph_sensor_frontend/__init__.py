"""
pH Sensor device plugin.

Declares FEATURE_FRAGMENTS matched against SiLA feature identifiers and
provides create_widget() for the app shell's device registry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from rxn_bench_ui.discovery import DiscoveredServer

FEATURE_FRAGMENTS: list[str] = [
    # Chembench native
    "PHSensor",
    # SiLA standard pH / potentiometry
    "PHMeasurement",
    "pHController",
    "PhMeter",
    "PotentialMeasure",
]


def create_widget(server: "DiscoveredServer", theme: dict) -> "QWidget":
    """Instantiate and return a PHSensorWidget for the given server."""
    from .widget import PHSensorWidget
    return PHSensorWidget(server, theme)
