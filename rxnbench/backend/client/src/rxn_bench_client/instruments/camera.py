"""Webcam/machine-vision camera instrument wrapper."""

from __future__ import annotations

from sila2.client import SilaClient

from ._util import _once


class Camera:
    """Webcam/machine-vision camera. Attach via bench.connect("camera", Camera, server=...).

    Examples::

        bench.connect("camera", Camera, server="rxn-bench-camera")

        image_bytes = bench.camera.snapshot()      # most recent captured frame
        bench.camera.save_snapshot("well_a1.jpg")   # capture and write to disk
        bench.camera.set_capture_interval(10.0)     # capture every 10s instead
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the camera server.
        """
        self._c = sila

    def snapshot(self) -> bytes:
        """Return the most recently captured frame as JPEG-encoded bytes."""
        return _once(self._c.Camera.LatestImage)

    def save_snapshot(self, path: str) -> None:
        """Capture the current frame and write it to a local file."""
        with open(path, "wb") as f:
            f.write(self.snapshot())

    def set_capture_interval(self, seconds: float) -> None:
        """Change how often the server captures (and archives) a new frame."""
        self._c.Camera.SetCaptureInterval(Seconds=seconds)
