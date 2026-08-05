"""Shared enums for the rxn bench hardware layer."""
from enum import Enum


class CalibrationPoint(str, Enum):
    """Valid calibration points for the Atlas Scientific pH probe."""
    MID = "mid"
    LOW = "low"
    HIGH = "high"
    CLEAR = "clear"
