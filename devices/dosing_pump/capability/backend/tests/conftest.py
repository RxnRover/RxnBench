"""Redirect session log output to a temp dir so tests never write into logs/.

SessionLog.__init__'s log_dir default is bound to _LOG_DIR at import time (a
plain Python default-argument, not a live lookup), so patching the module
attribute alone has no effect - the __init__ defaults tuple itself must be
patched instead.
"""
import pytest
import rxn_bench_dosing_pump.session_log as _session_log


@pytest.fixture(autouse=True)
def isolated_log_dir(tmp_path, monkeypatch):
    prefix_default, max_days_default, _log_dir_default = _session_log.SessionLog.__init__.__defaults__
    monkeypatch.setattr(
        _session_log.SessionLog.__init__,
        "__defaults__",
        (prefix_default, max_days_default, tmp_path),
    )
