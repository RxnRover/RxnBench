"""Redirect workspace state file to a temp dir so tests never touch ~/.chem_bench."""
import pytest
import chem_bench_gantry.workspace_manager as _wm


@pytest.fixture(autouse=True)
def isolated_workspace_state(tmp_path, monkeypatch):
    monkeypatch.setattr(_wm, "_STATE_FILE", tmp_path / "workspace.yaml")
