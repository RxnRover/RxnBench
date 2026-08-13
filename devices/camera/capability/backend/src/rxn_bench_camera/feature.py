"""SiLA2 feature definition for the camera device.

This is what the SiLA protocol exposes to clients (frontend, experiment
scripts). It depends only on CameraProtocol - never on a concrete driver.
"""
import asyncio

from unitelabs.cdk import sila

from rxn_bench_camera.image_log import ImageLog
from rxn_bench_camera.interfaces import CameraProtocol
from rxn_bench_camera.session_log import SessionLog

_DEFAULT_INTERVAL_S = 30.0


class Camera(sila.Feature):
    """SiLA2 Camera feature. Streams periodic snapshots and archives each capture."""

    def __init__(self, camera: CameraProtocol, capture_interval_s: float = _DEFAULT_INTERVAL_S) -> None:
        super().__init__(
            originator="edu.iastate.ames",
            category="rxnbench",
            version="1.0",
            maturity_level="Draft",
        )
        self._camera = camera
        self._interval = capture_interval_s
        self._log = SessionLog(prefix="camera")
        self._images = ImageLog(prefix="camera")

    @sila.ObservableProperty()
    async def latest_image(self) -> sila.Stream[bytes]:
        """
        Returns:
            LatestImage: Most recently captured still image, JPEG-encoded.
        """
        while True:
            image = await asyncio.to_thread(self._camera.capture)
            path = self._images.save(image)
            self._log.log("capture", file=path.name, size_bytes=len(image))
            yield image
            await asyncio.sleep(self._interval)

    @sila.UnobservableCommand()
    async def set_capture_interval(self, seconds: float) -> None:
        """
        Change how often latest_image captures and archives a new frame.

        Args:
            Seconds: New interval between captures, in seconds. Must be positive.
        """
        if seconds <= 0:
            raise ValueError("Capture interval must be positive.")
        self._interval = seconds
        self._log.log("set_capture_interval", seconds=seconds)
