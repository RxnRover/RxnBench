"""Tests for the Crowsnest HTTP camera driver."""
from unittest.mock import Mock, patch

from rxn_bench_camera.crowsnest_camera import CrowsnestCamera


def test_capture_hits_snapshot_url_and_returns_content():
    fake_response = Mock(content=b"\xff\xd8\xff\xe0jpegdata")
    with patch("rxn_bench_camera.crowsnest_camera.requests.get", return_value=fake_response) as get:
        camera = CrowsnestCamera("http://sv08.local:8080")
        image = camera.capture()

    get.assert_called_once()
    assert get.call_args.args[0] == "http://sv08.local:8080/snapshot"
    fake_response.raise_for_status.assert_called_once()
    assert image == b"\xff\xd8\xff\xe0jpegdata"


def test_base_url_trailing_slash_and_custom_snapshot_path():
    fake_response = Mock(content=b"x")
    with patch("rxn_bench_camera.crowsnest_camera.requests.get", return_value=fake_response) as get:
        camera = CrowsnestCamera("http://sv08.local:8080/", snapshot_path="/webcam/?action=snapshot")
        camera.capture()

    assert get.call_args.args[0] == "http://sv08.local:8080/webcam/?action=snapshot"
