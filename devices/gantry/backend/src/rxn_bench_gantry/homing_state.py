"""
Persists calibrated axis limits to ~/.rxn_bench/homing_state.json after a clean
SaveAndPark. Invalidated (file deleted) if the server exits uncleanly, the toolhead
changes, or the user re-homes.
"""
import json
import time
from pathlib import Path

_STATE_FILE = Path.home() / ".rxn_bench" / "homing_state.json"


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
    """Write calibrated axis limits to ``~/.rxn_bench/homing_state.json``.

    Args:
        x_min: Calibrated left X limit in mm.
        x_max: Calibrated right X limit in mm.
        y_min: Calibrated front Y limit in mm.
        y_max: Calibrated back Y limit in mm.
        clearance_z: Safe travel altitude in mm.
        toolhead_name: Name of the active toolhead at save time.
        is_calibrated: Whether the limits were measured in this session (always True on save).
    """
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
    """Return the saved state dict, or None if missing or not a clean shutdown.

    The file is only considered valid when ``clean_shutdown`` is True. An unclean
    shutdown (crash, power loss, or explicit :func:`invalidate` call) causes this
    function to return None so stale limits are never applied automatically.

    Returns:
        Dict with axis limits and toolhead name, or None if unavailable.
    """
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
