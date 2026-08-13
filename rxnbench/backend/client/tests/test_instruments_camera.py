"""Tests for the Camera instrument wrapper."""
from rxn_bench_client.instruments.camera import Camera

from .conftest import FakeSubscription


class _FakeImageProperty:
    def __init__(self, image: bytes):
        self._image = image

    def subscribe(self):
        return FakeSubscription(self._image)


class _FakeCameraFeature:
    def __init__(self, image: bytes):
        self.LatestImage = _FakeImageProperty(image)
        self.set_capture_interval_calls: list[float] = []

    def SetCaptureInterval(self, Seconds):
        self.set_capture_interval_calls.append(Seconds)


class _FakeCameraSila:
    def __init__(self, image: bytes):
        self.Camera = _FakeCameraFeature(image)


def test_snapshot_returns_latest_image_bytes():
    camera = Camera(_FakeCameraSila(b"\xff\xd8\xff\xe0jpegdata"))
    assert camera.snapshot() == b"\xff\xd8\xff\xe0jpegdata"


def test_save_snapshot_writes_bytes_to_file(tmp_path):
    camera = Camera(_FakeCameraSila(b"\xff\xd8\xff\xe0jpegdata"))
    path = tmp_path / "frame.jpg"
    camera.save_snapshot(str(path))
    assert path.read_bytes() == b"\xff\xd8\xff\xe0jpegdata"


def test_set_capture_interval_forwards_seconds():
    sila = _FakeCameraSila(b"x")
    Camera(sila).set_capture_interval(10.0)
    assert sila.Camera.set_capture_interval_calls == [10.0]
