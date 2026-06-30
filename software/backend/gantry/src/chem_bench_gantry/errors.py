"""Custom exceptions for the gantry hardware layer."""


class MotionLimitError(Exception):
    """Raised when a requested move would exceed the safe working envelope."""
