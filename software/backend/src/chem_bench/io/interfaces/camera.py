"""
Interface contract for camera clients.

CameraClientProtocol defines the minimum surface a camera client must provide.
CrowsnestClient satisfies this structurally. Any future camera backend
(USB webcam, RTSP stream, machine-vision camera) only needs to match these
two methods to be used by a camera SiLA feature.

Author: John Brittain
Date: Jun 18 2026
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CameraClientProtocol(Protocol):
    """Minimum interface required by a camera SiLA feature.

    Implemented by CrowsnestClient. A future camera backend (direct V4L2,
    RTSP, or machine-vision driver) only needs to satisfy these two methods.
    """

    def get_snapshot(self) -> bytes:
        """Capture a single frame and return it as JPEG bytes."""
        ...

    def get_stream_url(self) -> str:
        """Return the URL of the live MJPEG stream."""
        ...
