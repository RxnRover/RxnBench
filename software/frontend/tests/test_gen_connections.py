"""Tests for the connection-boilerplate generator (scripts/gen_connections.py).

Covers the generator's output structure on a synthetic spec, plus a golden
check that every device's checked-in generated_connection.py matches its
connection_spec.yaml (the pytest twin of `make check-connections`).
"""
import sys
from pathlib import Path

import pytest
import yaml

_FRONTEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _FRONTEND_DIR.parents[1]
sys.path.insert(0, str(_FRONTEND_DIR / "scripts"))

from gen_connections import generate  # noqa: E402


_SYNTHETIC_SPEC = yaml.safe_load("""
meta:
  package: sila2.example.test.v1
  service: TestDevice
  class_name: TestConnectionBase
  proto_module: rxn_bench_ui.devices.test.proto.test_pb2

streams:
  - rpc: Subscribe_Value
    decode_type: Subscribe_Value_Responses
    signal: value_updated
    signal_args: [float]
    emit: ["r.Value.value"]

  - rpc: Subscribe_Raw
    signal: raw_updated
    signal_args: [object]
    handler: _handle_raw

commands:
  - method: do_thing
    rpc: DoThing
    params: DoThing_Parameters
    args:
      - {name: amount, field: amount, type: float, default: 1.0}
  - {method: no_arg_cmd, rpc: NoArgCmd}
""")


@pytest.fixture
def code() -> str:
    return generate(_SYNTHETIC_SPEC, "test_spec.yaml")


def test_class_and_signals(code):
    assert "class TestConnectionBase(_FeatureConnection):" in code
    assert "value_updated = Signal(float)" in code
    assert "raw_updated = Signal(object)" in code


def test_typed_stream_gets_decode_kwarg(code):
    assert "decode=_pb.Subscribe_Value_Responses.FromString," in code
    assert 'lambda r: self.value_updated.emit(r.Value.value)' in code


def test_handler_stream_gets_abstract_stub(code):
    assert "self._handle_raw," in code
    assert "def _handle_raw(self, resp: Any) -> None:" in code
    assert "raise NotImplementedError" in code


def test_command_with_default_and_no_arg_command(code):
    assert "def do_thing(self, amount: float = 1.0) -> None:" in code
    assert "_p.amount.value = amount" in code
    assert 'self._fire(self._rpc("NoArgCmd"))' in code


def test_rpc_helper_uses_package_and_service(code):
    assert '_PKG = "sila2.example.test.v1"' in code
    assert '_SVC = "TestDevice"' in code


@pytest.mark.parametrize(
    "device", sorted(
        p.parents[1].name
        for p in (_REPO_ROOT / "devices").glob("*/frontend/connection_spec.yaml")
    ),
)
def test_checked_in_generated_connection_matches_spec(device):
    """Golden check: generated_connection.py is not stale for any device."""
    frontend = _REPO_ROOT / "devices" / device / "frontend"
    spec = yaml.safe_load((frontend / "connection_spec.yaml").read_text())
    # The header embeds the spec path passed on the command line; reproduce
    # the path make gen-connections uses.
    spec_path = f"../../devices/{device}/frontend/connection_spec.yaml"
    expected = generate(spec, spec_path) + "\n"
    actual = (frontend / "generated_connection.py").read_text()
    assert actual == expected, (
        f"{device}: generated_connection.py is stale - run `make gen-connections`"
    )
