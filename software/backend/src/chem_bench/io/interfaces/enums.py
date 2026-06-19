"""
Shared enums for the chem bench hardware layer.

Author: John Brittain
Date: Jun 17 2026
"""
from enum import Enum


class CalibrationPoint(str, Enum):
    """Valid calibration points for the Atlas Scientific pH probe."""
    MID = "mid"
    LOW = "low"
    HIGH = "high"
    CLEAR = "clear"
