"""Custom exceptions for the gantry hardware layer."""


class MotionLimitError(Exception):
    """Raised when a requested move would exceed the safe working envelope."""


class UnvalidatedGeometryError(Exception):
    """Raised when a workspace/well move is attempted with unmeasured toolhead geometry."""


class ExperimentLockError(Exception):
    """Raised when a command is rejected because another client holds the experiment lock."""


class ToolheadNotMountedError(Exception):
    """Raised when a well-targeted move is attempted with a toolhead that has not been confirmed mounted."""
