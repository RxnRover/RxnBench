"""
Smoke tests for FeatureDescriptor registry and identifier matching logic.

Verifies that the registry correctly maps server-reported identifiers to
display names using case-insensitive comparison — no gRPC connection needed.
"""
import pytest


# ── Inline the matching logic from sila_client to test it in isolation ────────
# (We can't import sila_client here because it requires PySide6 which is a
#  frontend dependency not available in the backend test environment.)

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
        identifier="edu.iastate.ames/chembench/Gantry/v0",
    ),
]


def _match_features(server_ids: list[str]) -> list[str]:
    """Mirror the matching logic in SilaClient._discover_and_stream."""
    return [
        fd.name for fd in _REGISTRY
        if any(sid.lower() == fd.identifier.lower() for sid in server_ids)
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_exact_match():
    ids = ["edu.iastate.ames/chembench/Gantry/v0"]
    assert _match_features(ids) == ["Gantry"]


def test_case_insensitive_match():
    ids = ["EDU.IASTATE.AMES/CHEMBENCH/GANTRY/V0"]
    assert _match_features(ids) == ["Gantry"]


def test_mixed_case_match():
    ids = ["Edu.Iastate.Ames/ChemBench/Gantry/v0"]
    assert _match_features(ids) == ["Gantry"]


def test_unrecognised_feature_ignored():
    ids = ["com.example/some/UnknownFeature/v1"]
    assert _match_features(ids) == []


def test_empty_server_list():
    assert _match_features([]) == []


def test_multiple_server_features_only_known_returned():
    ids = [
        "org.silastandard/core/SiLAService/v1",
        "edu.iastate.ames/chembench/Gantry/v0",
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
