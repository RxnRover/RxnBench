"""
Machine-specific configuration (axis limits, clearance height, Moonraker host).

Loaded from ~/.chem_bench/machine.yaml if present; falls back to built-in
defaults so the server starts without any config file.

Template (copy to ~/.chem_bench/machine.yaml and adjust for your machine):

    clearance_z: 50.0           # mm, safe Z height during XY travel
    x_min: 0.0
    x_max: 350.0                # mm, measured physical X travel
    y_min: 0.0
    y_max: 350.0                # mm, measured physical Y travel
    z_min: 0.0
    z_max: 340.0                # mm, measured physical Z travel
    moonraker_fallback_host: "192.168.10.2"   # used if auto-discovery fails

Author: John Brittain
Date: Jun 2026
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_CONFIG_FILE = Path.home() / ".chem_bench" / "machine.yaml"


@dataclass
class MachineConfig:
    clearance_z: float = 50.0
    x_min: float = 0.0
    x_max: float = 350.0
    y_min: float = 0.0
    y_max: float = 350.0
    z_min: float = 0.0
    z_max: float = 340.0
    moonraker_fallback_host: str = "192.168.10.2"

    @classmethod
    def load(cls) -> MachineConfig:
        """Load from ~/.chem_bench/machine.yaml, or return defaults if absent."""
        if not _CONFIG_FILE.exists():
            log.info("No machine.yaml found at %s — using defaults.", _CONFIG_FILE)
            return cls()
        try:
            data = yaml.safe_load(_CONFIG_FILE.read_text()) or {}
            cfg = cls(
                clearance_z=float(data.get("clearance_z", cls.clearance_z)),
                x_min=float(data.get("x_min", cls.x_min)),
                x_max=float(data.get("x_max", cls.x_max)),
                y_min=float(data.get("y_min", cls.y_min)),
                y_max=float(data.get("y_max", cls.y_max)),
                z_min=float(data.get("z_min", cls.z_min)),
                z_max=float(data.get("z_max", cls.z_max)),
                moonraker_fallback_host=str(
                    data.get("moonraker_fallback_host", cls.moonraker_fallback_host)
                ),
            )
            log.info("Machine config loaded from %s", _CONFIG_FILE)
            return cfg
        except Exception as exc:
            log.warning("Failed to parse machine.yaml (%s) — using defaults.", exc)
            return cls()
