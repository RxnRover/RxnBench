"""Tests for MachineConfig: defaults and per-field YAML overrides."""
import pytest

import rxn_bench_gantry.machine_config as mc
from rxn_bench_gantry.machine_config import MachineConfig


@pytest.fixture(autouse=True)
def isolated_config_file(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_CONFIG_FILE", tmp_path / "machine.yaml")


def test_defaults_without_file():
    cfg = MachineConfig.load()
    assert cfg.moonraker_fallback_host == "192.168.10.2"
    assert cfg.z_clearance_padding_mm == pytest.approx(5.0)


def test_z_clearance_padding_overridden_from_yaml():
    mc._CONFIG_FILE.write_text("z_clearance_padding_mm: 12.5\n")
    cfg = MachineConfig.load()
    assert cfg.z_clearance_padding_mm == pytest.approx(12.5)


def test_moonraker_fallback_host_overridden_from_yaml_leaves_padding_default():
    mc._CONFIG_FILE.write_text("moonraker_fallback_host: 10.0.0.5\n")
    cfg = MachineConfig.load()
    assert cfg.moonraker_fallback_host == "10.0.0.5"
    assert cfg.z_clearance_padding_mm == pytest.approx(5.0)


def test_malformed_yaml_falls_back_to_defaults():
    mc._CONFIG_FILE.write_text("not: valid: yaml: [")
    cfg = MachineConfig.load()
    assert cfg.z_clearance_padding_mm == pytest.approx(5.0)
