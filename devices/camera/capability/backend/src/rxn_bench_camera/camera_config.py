"""Machine-specific configuration loaded from ~/.rxn_bench/machine.yaml.
Falls back to built-in defaults if the file is absent.

Shares that file with the gantry package's own MachineConfig (both describe
settings for the same physical bench machine, e.g. the SOVOL SV08 hosting
both Moonraker and Crowsnest) - see CURRENT_STATE.md's note on duplicating
small per-device config loaders rather than importing across device packages.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_CONFIG_FILE = Path.home() / ".rxn_bench" / "machine.yaml"


@dataclass
class CameraConfig:
    """Crowsnest connection settings and default capture cadence.

    capture_interval_s trades off live-view responsiveness and archived
    image-log storage growth against each other - shorten it for tighter
    monitoring, lengthen it if logs/images/ is outgrowing the host's storage.
    """

    crowsnest_base_url:     str   = "http://sv08.local:8080"
    crowsnest_snapshot_path: str  = "/snapshot"
    capture_interval_s:     float = 30.0

    @classmethod
    def load(cls) -> CameraConfig:
        """Load from ~/.rxn_bench/machine.yaml, or return defaults if absent."""
        if not _CONFIG_FILE.exists():
            log.info("No machine.yaml found at %s - using defaults.", _CONFIG_FILE)
            return cls()
        try:
            data = yaml.safe_load(_CONFIG_FILE.read_text()) or {}
            cfg = cls(
                crowsnest_base_url=str(
                    data.get("crowsnest_base_url", cls.crowsnest_base_url)
                ),
                crowsnest_snapshot_path=str(
                    data.get("crowsnest_snapshot_path", cls.crowsnest_snapshot_path)
                ),
                capture_interval_s=float(
                    data.get("capture_interval_s", cls.capture_interval_s)
                ),
            )
            log.info("Camera config loaded from %s", _CONFIG_FILE)
            return cfg
        except Exception as exc:
            log.warning("Failed to parse machine.yaml (%s) - using defaults.", exc)
            return cls()
