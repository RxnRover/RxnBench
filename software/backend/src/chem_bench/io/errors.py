"""
Custom exceptions for the chem bench hardware layer.

Raise these for expected failure modes so SiLA features can surface
them as Defined Execution Errors with clear messages.

Author: John Brittain
Date: Jun 17 2026
"""


class DeviceNotFoundError(Exception):
    """Raised when a hardware device cannot be found on its bus."""


class DeviceCommunicationError(Exception):
    """Raised when a command to a device fails or returns an unexpected response."""


class CalibrationError(Exception):
    """Raised when a calibration operation fails."""


class MotionLimitError(Exception):
    """Raised when a requested move would exceed the safe working envelope."""
