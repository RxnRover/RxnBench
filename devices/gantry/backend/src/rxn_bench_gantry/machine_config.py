"""
Machine-specific configuration loaded from ~/.rxn_bench/machine.yaml.
Falls back to built-in defaults if the file is absent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_CONFIG_FILE = Path.home() / ".rxn_bench" / "machine.yaml"


@dataclass
class MachineConfig:
    """Per-machine Moonraker connection config.

    Axis limits are not here: they come from the motion client's own
    get_axis_limits() at server startup (Klipper's configured travel range,
    or the mock's fixed simulated bed), with manual homing and its saved
    state always taking precedence once calibrated. Keeping a second,
    separately maintained copy of the same numbers here was a real source of
    drift - only moonraker_fallback_host is a genuinely separate setting.
    """

    moonraker_fallback_host: str = "192.168.10.2"

    @classmethod
    def load(cls) -> MachineConfig:
        """Load from ~/.rxn_bench/machine.yaml, or return defaults if absent."""
        if not _CONFIG_FILE.exists():
            log.info("No machine.yaml found at %s - using defaults.", _CONFIG_FILE)
            return cls()
        try:
            data = yaml.safe_load(_CONFIG_FILE.read_text()) or {}
            cfg = cls(
                moonraker_fallback_host=str(
                    data.get("moonraker_fallback_host", cls.moonraker_fallback_host)
                ),
            )
            log.info("Machine config loaded from %s", _CONFIG_FILE)
            return cfg
        except Exception as exc:
            log.warning("Failed to parse machine.yaml (%s) - using defaults.", exc)
            return cls()
