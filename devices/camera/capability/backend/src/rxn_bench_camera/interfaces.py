"""Hardware interface contract for camera devices.

Any camera implementation (Crowsnest, a future direct-USB driver, etc.) only
needs to satisfy this - the SiLA feature never depends on a concrete driver.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CameraProtocol(Protocol):
    """Minimum interface required by the Camera SiLA feature."""

    def capture(self) -> bytes:
        """Capture and return a single still image as JPEG-encoded bytes."""
        ...
