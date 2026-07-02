"""Redirect on-disk state files to a temp dir so tests never touch ~/.rxn_bench."""
import pytest

import rxn_bench_gantry.homing_state as _hs
import rxn_bench_gantry.workspace_manager as _wm


@pytest.fixture(autouse=True)
def isolated_state_files(tmp_path, monkeypatch):
    monkeypatch.setattr(_wm, "_STATE_FILE", tmp_path / "workspace.yaml")
    monkeypatch.setattr(_hs, "_STATE_FILE", tmp_path / "homing_state.json")
