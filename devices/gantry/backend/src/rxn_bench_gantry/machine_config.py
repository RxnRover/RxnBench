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

    # Safety margin added on top of the tallest loaded labware's top surface
    # when computing safe clearance-travel height, to absorb measurement
    # error in labware/toolhead geometry. Per-machine (not per-labware)
    # because it is about the operator's confidence in *this bench's*
    # measurements, not a physical property of any one plate.
    z_clearance_padding_mm: float = 5.0

    # Safety gap kept above a well's bottom when engaging. The engagement
    # descent is the mean of the toolhead's configured z_engage and the well's
    # own measured depth (so it adapts to the labware instead of trusting one
    # hand-tuned number), then capped so the tip stops at least this far above
    # the well bottom - even when z_engage is configured deeper than the well.
    # Per-machine for the same reason as z_clearance_padding_mm: it reflects
    # confidence in this bench's geometry measurements, not any one plate.
    engage_bottom_margin_mm: float = 2.0

    # X-gantry crossbar collision model. The carriage rides on a horizontal
    # crossbar spanning (full) X at the carriage's Y; lowering Z brings the whole
    # bar down, so descending to a low plate can drive the bar into a TALLER
    # plate sharing that Y-row even though the tip is clear. Both must be set for
    # the check to run - left as None (the default) the crossbar collision check
    # is disabled and motion behaves exactly as before.
    #   crossbar_clearance_above_tip_mm: with the tip at the bed (Z=0), the
    #     height of the crossbar's underside above the bed. In the workspace Z
    #     frame (Z = tip height) the bar's underside is always this far above the
    #     tip, so a plate top above `tip_Z + this` is a collision.
    #   crossbar_y_thickness_mm: the bar's extent in Y; only plates whose Y
    #     footprint overlaps the bar's Y band (carriage Y +/- thickness/2) are
    #     threatened. (The bar is assumed to span the full X travel.)
    crossbar_clearance_above_tip_mm: float | None = None
    crossbar_y_thickness_mm: float | None = None

    @classmethod
    def load(cls) -> MachineConfig:
        """Load from ~/.rxn_bench/machine.yaml, or return defaults if absent."""
        if not _CONFIG_FILE.exists():
            log.info("No machine.yaml found at %s - using defaults.", _CONFIG_FILE)
            return cls()
        try:
            data = yaml.safe_load(_CONFIG_FILE.read_text()) or {}

            def _opt_float(key: str) -> float | None:
                val = data.get(key)
                return float(val) if val is not None else None

            cfg = cls(
                moonraker_fallback_host=str(
                    data.get("moonraker_fallback_host", cls.moonraker_fallback_host)
                ),
                z_clearance_padding_mm=float(
                    data.get("z_clearance_padding_mm", cls.z_clearance_padding_mm)
                ),
                engage_bottom_margin_mm=float(
                    data.get("engage_bottom_margin_mm", cls.engage_bottom_margin_mm)
                ),
                crossbar_clearance_above_tip_mm=_opt_float("crossbar_clearance_above_tip_mm"),
                crossbar_y_thickness_mm=_opt_float("crossbar_y_thickness_mm"),
            )
            log.info("Machine config loaded from %s", _CONFIG_FILE)
            return cfg
        except Exception as exc:
            log.warning("Failed to parse machine.yaml (%s) - using defaults.", exc)
            return cls()
