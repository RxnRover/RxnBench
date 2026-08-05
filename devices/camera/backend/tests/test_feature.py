"""Tests for the Camera SiLA feature - the glue between CameraProtocol and the wire.

No pytest-asyncio dependency is used (the project has none); coroutines are
driven directly with asyncio.run(), matching how a real event loop would call
them one step at a time.
"""
import asyncio

import pytest

from rxn_bench_camera.feature import Camera


class _FakeCamera:
    def __init__(self, image: bytes = b"fake-jpeg-bytes"):
        self._image = image
        self.capture_calls = 0

    def capture(self) -> bytes:
        self.capture_calls += 1
        return self._image


async def _first_image(feature: Camera) -> bytes:
    gen = feature.latest_image()
    try:
        return await gen.__anext__()
    finally:
        await gen.aclose()


def test_latest_image_yields_camera_capture():
    camera = _FakeCamera(image=b"\xff\xd8\xff\xe0frame")
    feature = Camera(camera=camera, capture_interval_s=60.0)
    assert asyncio.run(_first_image(feature)) == b"\xff\xd8\xff\xe0frame"
    assert camera.capture_calls == 1


def test_set_capture_interval_updates_interval():
    feature = Camera(camera=_FakeCamera(), capture_interval_s=30.0)
    asyncio.run(feature.set_capture_interval(5.0))
    assert feature._interval == 5.0


def test_set_capture_interval_rejects_non_positive():
    feature = Camera(camera=_FakeCamera(), capture_interval_s=30.0)
    with pytest.raises(ValueError):
        asyncio.run(feature.set_capture_interval(0.0))
    with pytest.raises(ValueError):
        asyncio.run(feature.set_capture_interval(-1.0))
