"""Tests for the in-memory mock camera."""
from rxn_bench_camera.interfaces import CameraProtocol
from rxn_bench_camera.mock_camera import MockCamera


def test_mock_satisfies_protocol():
    assert isinstance(MockCamera(), CameraProtocol)


def test_mock_capture_returns_valid_ppm_image():
    image = MockCamera().capture()
    assert isinstance(image, bytes)
    assert image.startswith(b"P6\n")


def test_mock_capture_is_repeatable():
    camera = MockCamera()
    assert camera.capture() == camera.capture()
