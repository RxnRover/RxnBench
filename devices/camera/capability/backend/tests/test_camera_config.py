"""Tests for CameraConfig.load()."""
from rxn_bench_camera.camera_config import CameraConfig


def test_load_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "rxn_bench_camera.camera_config._CONFIG_FILE", tmp_path / "missing.yaml"
    )
    cfg = CameraConfig.load()
    assert cfg == CameraConfig()


def test_load_reads_overrides(tmp_path, monkeypatch):
    config_file = tmp_path / "machine.yaml"
    config_file.write_text(
        "crowsnest_base_url: http://192.168.1.50:8080\n"
        "crowsnest_snapshot_path: /webcam/?action=snapshot\n"
        "capture_interval_s: 10\n"
    )
    monkeypatch.setattr("rxn_bench_camera.camera_config._CONFIG_FILE", config_file)
    cfg = CameraConfig.load()
    assert cfg.crowsnest_base_url == "http://192.168.1.50:8080"
    assert cfg.crowsnest_snapshot_path == "/webcam/?action=snapshot"
    assert cfg.capture_interval_s == 10.0


def test_load_falls_back_to_defaults_on_parse_error(tmp_path, monkeypatch):
    config_file = tmp_path / "machine.yaml"
    config_file.write_text("not: valid: yaml: [")
    monkeypatch.setattr("rxn_bench_camera.camera_config._CONFIG_FILE", config_file)
    cfg = CameraConfig.load()
    assert cfg == CameraConfig()
