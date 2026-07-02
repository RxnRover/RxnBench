"""
Smoke tests for FeatureDescriptor registry and identifier matching logic.

Verifies that the registry correctly maps server-reported identifiers to
display names using case-insensitive comparison - no gRPC connection needed.
"""
# sila_client can't be imported here - it requires PySide6, a frontend-only dependency.
import dataclasses
from typing import Callable


@dataclasses.dataclass(frozen=True)
class _FeatureDescriptor:
    name: str
    identifier: str
    start_streams: Callable = lambda *_: None


_REGISTRY = [
    _FeatureDescriptor(
        name="Gantry",
        identifier="edu.iastate.ames/rxnbench/Gantry/v0",
    ),
]


def _match_features(server_ids: list[str]) -> list[str]:
    """Mirror the matching logic in SilaClient._discover_and_stream."""
    return [
        fd.name for fd in _REGISTRY
        if any(sid.lower() == fd.identifier.lower() for sid in server_ids)
    ]



def test_exact_match():
    ids = ["edu.iastate.ames/rxnbench/Gantry/v0"]
    assert _match_features(ids) == ["Gantry"]


def test_case_insensitive_match():
    ids = ["EDU.IASTATE.AMES/RXNBENCH/GANTRY/V0"]
    assert _match_features(ids) == ["Gantry"]


def test_mixed_case_match():
    ids = ["Edu.Iastate.Ames/RxnBench/Gantry/v0"]
    assert _match_features(ids) == ["Gantry"]


def test_unrecognised_feature_ignored():
    ids = ["com.example/some/UnknownFeature/v1"]
    assert _match_features(ids) == []


def test_empty_server_list():
    assert _match_features([]) == []


def test_multiple_server_features_only_known_returned():
    ids = [
        "org.silastandard/core/SiLAService/v1",
        "edu.iastate.ames/rxnbench/Gantry/v0",
        "com.vendor/unknown/Feature/v2",
    ]
    result = _match_features(ids)
    assert "Gantry" in result
    assert len(result) == 1


def test_registry_identifiers_are_unique():
    identifiers = [fd.identifier.lower() for fd in _REGISTRY]
    assert len(identifiers) == len(set(identifiers)), "Duplicate identifiers in registry"


def test_registry_names_are_unique():
    names = [fd.name for fd in _REGISTRY]
    assert len(names) == len(set(names)), "Duplicate display names in registry"
