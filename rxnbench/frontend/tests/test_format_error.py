"""Tests for _format_error - the gRPC exception -> operator message heuristic."""
import base64

from rxn_bench_ui.connections.base import _format_error


def _grpc_style_exception(details: str) -> Exception:
    """Mimic str(grpc.RpcError) shape: a details = "..." line inside the repr."""
    return Exception(
        '<_InactiveRpcError of RPC that terminated with:\n'
        '\tstatus = StatusCode.ABORTED\n'
        f'\tdetails = "{details}"\n'
        '>'
    )


def test_decodes_base64_details_and_extracts_known_marker():
    payload = base64.b64encode(
        b"Traceback (most recent call last)...\nMotionLimitError: X=999.0 exceeds X limits [0, 300]"
    ).decode()
    msg = _format_error("MoveTo", _grpc_style_exception(payload))
    assert msg.startswith("MotionLimitError: X=999.0")


def test_decodes_experiment_lock_error_marker():
    payload = base64.b64encode(
        b"ExperimentLockError: Rejected: an experiment script holds the gantry lock."
    ).decode()
    msg = _format_error("Jog", _grpc_style_exception(payload))
    assert msg.startswith("ExperimentLockError: Rejected")


def test_plain_details_pass_through():
    msg = _format_error("Jog", _grpc_style_exception("connection refused"))
    assert msg == "connection refused"


def test_unparseable_exception_falls_back_to_method_name():
    assert _format_error("Jog", Exception("boom")) == "Jog failed"
