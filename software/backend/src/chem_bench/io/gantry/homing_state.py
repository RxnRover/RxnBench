"""
Homing state persistence.

Saves calibrated axis limits and Z reference to a JSON file after a clean
SaveAndPark shutdown. On restart the controller loads this file and restores
the limits so the user doesn't have to re-home every time.

State is invalidated (file deleted) if:
  - The server exits without a clean SaveAndPark call.
  - The active toolhead changes.
  - The user explicitly re-homes.

Author: John Brittain
Date: Jun 18 2026
"""
import json
import time
from pathlib import Path

_STATE_FILE = Path.home() / ".chem_bench" / "homing_state.json"


def save(
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    clearance_z: float,
    toolhead_name: str,
    is_calibrated: bool = True,
) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "clearance_z": clearance_z,
        "toolhead_name": toolhead_name,
        "clean_shutdown": True,
        "is_calibrated": is_calibrated,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _STATE_FILE.write_text(json.dumps(data, indent=2))


def load() -> dict | None:
    """Return the saved state dict or None if missing / not a clean shutdown."""
    if not _STATE_FILE.exists():
        return None
    try:
        data = json.loads(_STATE_FILE.read_text())
        if not data.get("clean_shutdown"):
            return None
        return data
    except Exception:
        return None


def invalidate() -> None:
    """Mark the saved state as dirty so it won't be auto-loaded next time."""
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text())
            data["clean_shutdown"] = False
            _STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            _STATE_FILE.unlink(missing_ok=True)
