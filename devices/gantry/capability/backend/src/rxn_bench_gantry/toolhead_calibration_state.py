"""Persists measured toolhead tip offsets to ~/.rxn_bench/toolhead_calibration.json.

Keyed by toolhead name so each physical head keeps its own measured tip_x/tip_y/
tip_offset_z across restarts and toolhead switches, independent of the bundled
YAML config (which stays an unmeasured placeholder until this file has an
entry for it). The XY calibration (rim points) and Z calibration (surface
touch) are separate wizard steps that may run independently, so entries are
merged field-by-field rather than overwritten wholesale.
"""
import json
from datetime import datetime
from pathlib import Path

_STATE_FILE = Path.home() / ".rxn_bench" / "toolhead_calibration.json"


def save(name: str, **fields: float) -> str:
    """Persist measured calibration fields for one toolhead, merging with any existing entry.

    Every save stamps a fresh ``calibrated_at`` timestamp, even a Z-only or
    XY-only save - it marks when the toolhead's calibration state last
    changed, not which specific field was touched.

    Args:
        name: Toolhead name matching a config folder under ``toolheads/``.
        **fields: Measured values to store, e.g. ``tip_x=``, ``tip_y=``, ``tip_offset_z=``.

    Returns:
        The ISO timestamp stamped for this save.
    """
    data = _read_all()
    entry = data.get(name, {})
    entry.update(fields)
    timestamp = datetime.now().isoformat(timespec="seconds")
    entry["calibrated_at"] = timestamp
    data[name] = entry
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(data, indent=2))
    return timestamp


def load(name: str) -> dict | None:
    """Return the saved calibration fields for *name*, or None if nothing has been measured yet."""
    return _read_all().get(name)


def _read_all() -> dict:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:
        return {}
