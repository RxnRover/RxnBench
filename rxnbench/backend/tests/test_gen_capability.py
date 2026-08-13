"""Drift checks for gen_capability.py's output vs. the checked-in files.

Covers interfaces.py / <Feature>.capability.md golden-file drift, plus a
static cross-check that feature.py's declared SiLA surface still corresponds
to what each spec declares.

This test needs no device-specific venv or hardware deps - it works entirely
from `ast`-parsed source text and `yaml`-parsed specs, so it lives centrally
here rather than duplicated into each device's own tests/ directory.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest
import yaml

_TESTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _TESTS_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parents[1]

sys.path.insert(0, str(_BACKEND_DIR / "scripts"))
from gen_capability import (  # noqa: E402
    _BEGIN_MARKER,
    _END_MARKER,
    generate_doc,
    generate_interfaces,
    generate_interfaces_block,
)


def _capability_specs() -> list[Path]:
    return sorted(_REPO_ROOT.glob("devices/*/capability/backend/src/*/*.capability.yaml"))


def test_capability_spec_glob_finds_specs() -> None:
    # Explicit guard against the exact stale-glob bug found in
    # rxnbench/frontend/tests/test_gen_connections.py: a wrong glob there
    # silently collects zero parametrized cases instead of failing. Fail
    # loudly here instead if this glob ever stops matching real specs.
    specs = _capability_specs()
    assert len(specs) >= 1, (
        "No *.capability.yaml files matched devices/*/capability/backend/src/*/ - "
        "the glob in this test is stale, fix it before trusting the parametrized "
        "tests below."
    )


def _load(spec_path: Path) -> dict:
    return yaml.safe_load(spec_path.read_text())


def _rel(spec_path: Path) -> str:
    # Matches exactly the string the Makefile's `gen-capability`/`check-capability`
    # targets pass on the command line (a `../../devices/...` path relative to
    # rxnbench/backend/, since that's where `uv run` is invoked from) - the
    # "Source:" comment embedded in generated output must match this exactly,
    # or this golden-file test spuriously fails on a cosmetic path-string mismatch.
    return os.path.relpath(spec_path, _BACKEND_DIR)


@pytest.mark.parametrize("spec_path", _capability_specs(), ids=lambda p: p.parent.name)
def test_checked_in_interfaces_matches_spec(spec_path: Path) -> None:
    spec = _load(spec_path)
    interfaces_path = spec_path.parent / "interfaces.py"
    actual = interfaces_path.read_text()

    if spec.get("excluded_protocols"):
        # Partially-generated file (gantry): only the marked block is owned
        # by the generator - compare that region only.
        expected_block = generate_interfaces_block(spec)
        actual_block = _extract_marked_block(actual, interfaces_path)
        assert actual_block == expected_block, (
            f"{interfaces_path}: the generated region (between {_BEGIN_MARKER!r} and "
            f"{_END_MARKER!r}) is stale - run 'make gen-capability'."
        )
    else:
        expected = generate_interfaces(spec, _rel(spec_path))
        assert actual == expected, f"{interfaces_path} is stale - run 'make gen-capability'."


def _extract_marked_block(text: str, path: Path) -> str:
    lines = text.split("\n")
    try:
        begin_i = next(i for i, l in enumerate(lines) if l.strip() == _BEGIN_MARKER)
        end_i = next(i for i, l in enumerate(lines) if l.strip() == _END_MARKER)
    except StopIteration:
        pytest.fail(f"{path}: missing BEGIN/END generated markers")
    # Skip the marker line itself and the "# Source: ..." line that follows it.
    return "\n".join(lines[begin_i + 2 : end_i])


@pytest.mark.parametrize("spec_path", _capability_specs(), ids=lambda p: p.parent.name)
def test_checked_in_doc_snapshot_matches_spec(spec_path: Path) -> None:
    spec = _load(spec_path)
    doc_path = spec_path.parent / f"{spec['meta']['feature_class']}.capability.md"
    expected = generate_doc(spec, _rel(spec_path))
    assert doc_path.read_text() == expected, f"{doc_path} is stale - run 'make gen-capability'."


# --- feature.py cross-check ---

def _hardware_refs(tree: ast.AST, hardware_attr: str) -> set[str]:
    """Every `self.<hardware_attr>.<name>` attribute access anywhere in the tree.

    Deliberately matches ALL ast.Attribute nodes, not just ast.Call nodes:
    dosing_pump and gantry route most hardware access through wrapper helpers
    (`self._run(self._pump.dispense_volume, ...)`,
    `asyncio.to_thread(self._camera.capture)`), where the hardware method
    appears as a bare attribute expression passed as an argument, never as
    `self._pump.dispense_volume(...)` directly. A Call-only matcher misses
    almost everything in those two files.
    """
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            inner = node.value
            if isinstance(inner.value, ast.Name) and inner.value.id == "self" and inner.attr == hardware_attr:
                refs.add(node.attr)
    return refs


def _require_gated_protocols(tree: ast.AST) -> set[str]:
    """Protocol names passed as the first arg to any `self._require(<Protocol>, ...)` call."""
    gated: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_require"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            gated.add(node.args[0].id)
    return gated


_SILA_DECORATORS = {"ObservableProperty", "UnobservableProperty", "ObservableCommand", "UnobservableCommand"}


def _sila_decorated_methods(tree: ast.AST, feature_class: str, path: Path) -> dict[str, ast.FunctionDef]:
    """Every method on `feature_class` decorated with one of the sila.* SiLA decorators."""
    assert "from unitelabs.cdk import sila" in ast.unparse(tree) or any(
        isinstance(n, ast.ImportFrom) and n.module == "unitelabs.cdk" and any(a.name == "sila" for a in n.names)
        for n in ast.walk(tree)
    ), (
        f"{path}: expected 'from unitelabs.cdk import sila' - decorator detection "
        "assumes that exact import shape and would otherwise silently find nothing."
    )

    cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == feature_class),
        None,
    )
    assert cls is not None, f"{path}: no class {feature_class!r} found"

    methods: dict[str, ast.FunctionDef] = {}
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in _SILA_DECORATORS
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "sila"
            ):
                methods[node.name] = node
                break
    return methods


@pytest.mark.parametrize("spec_path", _capability_specs(), ids=lambda p: p.parent.name)
def test_feature_hardware_calls_are_declared_in_spec(spec_path: Path) -> None:
    spec = _load(spec_path)
    feature_path = spec_path.parent / "feature.py"
    tree = ast.parse(feature_path.read_text())
    hw_attr = spec["meta"]["hardware_attr"]

    refs = _hardware_refs(tree, hw_attr)
    require_gated = _require_gated_protocols(tree)

    declared: set[str] = {m["name"] for p in spec["protocols"] for m in p["members"]}
    optional_members: dict[str, set[str]] = {
        p["name"]: {m["name"] for m in p["members"]} for p in spec["protocols"] if p.get("optional")
    }

    undeclared = refs - declared
    assert not undeclared, (
        f"{feature_path}: calls {sorted(undeclared)} on self.{hw_attr}, not declared "
        f"in any protocol in {spec_path.name} - update the spec."
    )

    for proto_name, members in optional_members.items():
        if refs & members and proto_name not in require_gated:
            pytest.fail(
                f"{feature_path}: uses {proto_name} members {sorted(refs & members)} "
                f"but has no `self._require({proto_name}, ...)` guard."
            )

    # Informational only, not asserted: a spec-declared member feature.py never
    # calls isn't necessarily spec drift (e.g. gantry's GantryControllerProtocol
    # currently declares get_workspace_name/home_auto, neither referenced by
    # feature.py today - pre-existing, out of scope for this check to fix).
    unreferenced_core = declared - set().union(*optional_members.values(), set()) - refs
    if unreferenced_core:
        print(f"NOTE {spec_path.name}: spec declares members feature.py never calls: {sorted(unreferenced_core)}")


@pytest.mark.parametrize("spec_path", _capability_specs(), ids=lambda p: p.parent.name)
def test_feature_only_members_match_spec(spec_path: Path) -> None:
    spec = _load(spec_path)
    feature_only = spec.get("feature_only", [])
    if not feature_only and not spec.get("protocols"):
        pytest.skip("nothing to check")

    feature_path = spec_path.parent / "feature.py"
    tree = ast.parse(feature_path.read_text())
    hw_attr = spec["meta"]["hardware_attr"]
    feature_class = spec["meta"]["feature_class"]

    decorated = _sila_decorated_methods(tree, feature_class, feature_path)
    declared_feature_only = {m["name"] for m in feature_only}

    stale = declared_feature_only - decorated.keys()
    assert not stale, (
        f"{spec_path.name}: feature_only entries {sorted(stale)} aren't decorated "
        f"SiLA members on {feature_class} in {feature_path} anymore - remove them from the spec."
    )

    undocumented = {
        name
        for name, node in decorated.items()
        if not _hardware_refs(node, hw_attr) and name not in declared_feature_only
    }
    assert not undocumented, (
        f"{feature_path}: {sorted(undocumented)} are decorated SiLA members with no "
        f"self.{hw_attr} reference (pure feature-local bookkeeping) but aren't declared "
        f"in {spec_path.name}'s feature_only list - add them."
    )
