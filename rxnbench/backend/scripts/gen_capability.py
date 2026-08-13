#!/usr/bin/env python3
"""
gen_capability.py - generate a device's interfaces.py + capability doc snapshot
from a declarative <FeatureClass>.capability.yaml spec.

Run from rxnbench/backend/:
    uv run python scripts/gen_capability.py \\
        ../../devices/ph_sensor/capability/backend/src/rxn_bench_ph/PHSensor.capability.yaml
    make gen-capability      # regenerate every device
    make check-capability    # CI drift check

What it generates (per spec):
    - interfaces.py: one @runtime_checkable Protocol class per `protocols` entry,
      pure signatures (no bodies beyond `...`).
    - <FeatureClass>.capability.md: a human-readable snapshot of the capability -
      feature identity, each Protocol's members, feature-only SiLA members, and
      protocols intentionally excluded from generation. This file is NOT consumed
      at runtime - the running SiLA server already produces an equivalent FDL live,
      via unitelabs-cdk's decorators on feature.py. It exists purely so the
      capability's shape is readable without connecting to a running server.

What it does NOT generate:
    - feature.py or any of its behavior (session logging, capability guards,
      experiment locks, unit/type transforms). interfaces.py is pure signatures
      in every device today - feature.py is not, and stays 100% hand-written.
    - Anything for `excluded_protocols` entries (e.g. gantry's MotionClientProtocol) -
      those are documentary only, printed in the doc snapshot, never touched here.

If a spec declares `excluded_protocols`, this script does NOT own the whole
interfaces.py file - it only replaces the text between two marker comments
(see _splice_generated_block), leaving any hand-written Protocol above the
markers untouched. Every other spec generates interfaces.py wholesale.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_BEGIN_MARKER = "# --- BEGIN GENERATED (gen_capability.py - do not edit below by hand) ---"
_END_MARKER = "# --- END GENERATED ---"

_LINE_LIMIT = 99  # empirically matches this repo's existing interfaces.py files


# --- docstring rendering ---

def _render_doc_block(doc: str, indent: str) -> list[str]:
    """Render `doc` (a possibly multi-line string) as a `\"\"\"...\"\"\"` docstring.

    Single-line docs collapse to one line (`\"\"\"Text.\"\"\"`); multi-line docs get
    the summary line after the opening `\"\"\"` and a closing `\"\"\"` on its own line,
    matching every current interfaces.py file in this repo. Internal formatting
    (blank lines, nested indentation for e.g. an Args: block) is preserved
    verbatim from the spec - this function only prefixes each line with `indent`,
    it never reflows text.
    """
    lines = doc.rstrip("\n").split("\n")
    if len(lines) == 1:
        return [f'{indent}"""{lines[0]}"""']
    out = [f'{indent}"""{lines[0]}']
    for line in lines[1:]:
        out.append(f"{indent}{line}" if line else "")
    out.append(f'{indent}"""')
    return out


# --- member (property/method) rendering ---

def _param_strs(params: list[dict]) -> list[str]:
    out = []
    for p in params:
        if "default" in p:
            out.append(f"{p['name']}: {p['type']} = {p['default']}")
        else:
            out.append(f"{p['name']}: {p['type']}")
    return out


def _render_member(m: dict, indent: str = "    ") -> list[str]:
    name = m["name"]
    returns = m.get("returns", "None")
    doc = m.get("doc")
    is_property = m.get("property", False)
    params = m.get("params", [])

    out: list[str] = []
    if is_property:
        out.append(f"{indent}@property")

    param_strs = ["self"] + _param_strs(params)
    one_line_sig = f"{indent}def {name}({', '.join(param_strs)}) -> {returns}:"

    if len(one_line_sig) <= _LINE_LIMIT:
        sig_lines = [one_line_sig]
    else:
        inner = indent + "    "
        sig_lines = [f"{indent}def {name}("]
        for p in param_strs:
            sig_lines.append(f"{inner}{p},")
        sig_lines.append(f"{indent}) -> {returns}:")

    if doc:
        # Doc form: signature ends in ':', docstring + '...' follow on their own lines.
        out += sig_lines
        out += _render_doc_block(doc, indent + "    ")
        out.append(f"{indent}    ...")
    else:
        # Terse form: '...' appended to the last signature line instead of a body.
        sig_lines[-1] = sig_lines[-1] + " ..."
        out += sig_lines

    return out


# --- protocol (class) rendering ---

def _render_protocol(p: dict) -> list[str]:
    out = ["@runtime_checkable", f"class {p['name']}(Protocol):"]
    if p.get("doc"):
        out += _render_doc_block(p["doc"], "    ")
        out.append("")
    members = p.get("members", [])
    for i, m in enumerate(members):
        out += _render_member(m)
        if i < len(members) - 1:
            out.append("")
    return out


# --- top-level generators ---

def generate_interfaces_block(spec: dict) -> str:
    """Render just the generated Protocol class(es), no header/imports - used
    both for a spec's own standalone interfaces.py and for splicing into a
    partially hand-written file (see _splice_generated_block)."""
    protocols = spec["protocols"]
    out: list[str] = []
    for i, p in enumerate(protocols):
        out += _render_protocol(p)
        if i < len(protocols) - 1:
            out += ["", ""]
    return "\n".join(out)


def generate_interfaces(spec: dict, spec_path: str) -> str:
    meta = spec["meta"]
    out: list[str] = []
    out += _render_doc_block(meta["summary"].strip(), "")
    out += [
        "# Generated by rxnbench/backend/scripts/gen_capability.py - do not edit by hand.",
        f"# Source: {spec_path}",
        "# Regenerate (from rxnbench/backend):",
        f"#   uv run python scripts/gen_capability.py {spec_path}",
        "from __future__ import annotations",
        "",
        "from typing import Protocol, runtime_checkable",
        "",
    ]
    for imp in spec.get("imports", []):
        out.append(imp)
    if spec.get("imports"):
        out.append("")
    out.append("")
    out.append(generate_interfaces_block(spec))
    out.append("")
    return "\n".join(out)


def _splice_generated_block(existing_text: str, spec: dict, spec_path: str) -> str:
    """Replace only the text between the BEGIN/END markers in an existing
    interfaces.py, leaving any hand-written Protocol(s) above untouched."""
    lines = existing_text.split("\n")
    try:
        begin_i = next(i for i, l in enumerate(lines) if l.strip() == _BEGIN_MARKER)
        end_i = next(i for i, l in enumerate(lines) if l.strip() == _END_MARKER)
    except StopIteration:
        raise ValueError(
            f"{spec_path}: spec declares excluded_protocols, so its interfaces.py "
            f"must contain the marker comments:\n  {_BEGIN_MARKER}\n  ...\n  {_END_MARKER}\n"
            "Add them by hand around the block this generator owns before regenerating."
        )
    if end_i <= begin_i:
        raise ValueError(f"{spec_path}: END marker appears before BEGIN marker in interfaces.py")

    block = [
        _BEGIN_MARKER,
        f"# Source: {spec_path}",
        generate_interfaces_block(spec),
        _END_MARKER,
    ]
    return "\n".join(lines[: begin_i] + block + lines[end_i + 1 :])


# --- doc snapshot ---

def _doc_member_row(m: dict) -> str:
    params = ", ".join(_param_strs(m.get("params", [])))
    sig = f"() -> {m.get('returns', 'None')}" if not params else f"({params}) -> {m.get('returns', 'None')}"
    desc = (m.get("doc") or "").strip().split("\n")[0]
    return f"| `{m['name']}` | `{sig}` | {desc} |"


def _doc_protocol_section(p: dict, heading: str) -> list[str]:
    out = [heading, ""]
    if p.get("doc"):
        out += [p["doc"].strip().split("\n")[0], ""]
    out += ["| Member | Signature | Description |", "|---|---|---|"]
    for m in p.get("members", []):
        out.append(_doc_member_row(m))
    out.append("")
    return out


def generate_doc(spec: dict, spec_path: str) -> str:
    meta = spec["meta"]
    feature_class = meta["feature_class"]
    out = [
        f"# {feature_class} capability",
        "",
        "Generated by `rxnbench/backend/scripts/gen_capability.py` - do not edit by hand.",
        f"Source: `{spec_path}`",
        "",
        "This is a portable, human-readable snapshot for documentation purposes only.",
        "It is not consumed at runtime - the running SiLA server derives an equivalent",
        "FDL description live from `feature.py`'s `unitelabs.cdk` decorators.",
        "",
        "## Feature identity",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Originator | {meta['originator']} |",
        f"| Category | {meta['category']} |",
        f"| Version | {meta['version']} |",
        f"| Maturity level | {meta['maturity_level']} |",
        "",
        f"> {meta['summary'].strip()}",
        "",
    ]

    core = [p for p in spec["protocols"] if p.get("core")]
    optional = [p for p in spec["protocols"] if p.get("optional")]
    for p in core:
        out += _doc_protocol_section(p, f"## Driver-facing Protocol: `{p['name']}` (core, required)")
    for p in optional:
        out += _doc_protocol_section(
            p, f"## Optional Protocol: `{p['name']}` (gated by `self._require(...)` at runtime)"
        )

    out.append("## Feature-only SiLA members (no driver-Protocol backing)")
    out.append("")
    feature_only = spec.get("feature_only", [])
    if not feature_only:
        out.append("_None for this device._")
        out.append("")
    else:
        out += ["| Member | Kind | Signature | Description |", "|---|---|---|---|"]
        for m in feature_only:
            params = ", ".join(_param_strs(m.get("params", [])))
            sig = f"() -> {m.get('returns', 'None')}" if not params else f"({params}) -> {m.get('returns', 'None')}"
            desc = (m.get("doc") or "").strip().split("\n")[0]
            out.append(f"| `{m['name']}` | {m['sila_kind']} | `{sig}` | {desc} |")
        out.append("")

    excluded = spec.get("excluded_protocols", [])
    if excluded:
        out.append("## Out of scope")
        out.append("")
        for e in excluded:
            out.append(f"- **`{e['name']}`**: {e['reason'].strip()}")
        out.append("")

    return "\n".join(out)


# --- entry point ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", help="Path to the <FeatureClass>.capability.yaml spec file")
    parser.add_argument("--out-interfaces", help="Output path for interfaces.py (default: alongside spec)")
    parser.add_argument("--out-doc", help="Output path for the doc snapshot (default: alongside spec)")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"error: spec not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    spec = yaml.safe_load(spec_path.read_text())

    out_interfaces = Path(args.out_interfaces) if args.out_interfaces else spec_path.parent / "interfaces.py"
    out_doc = (
        Path(args.out_doc)
        if args.out_doc
        else spec_path.parent / f"{spec['meta']['feature_class']}.capability.md"
    )

    if spec.get("excluded_protocols"):
        existing = out_interfaces.read_text() if out_interfaces.exists() else ""
        if not existing:
            print(
                f"error: {out_interfaces} must already exist (with BEGIN/END markers) "
                "when the spec declares excluded_protocols - this generator only splices "
                "into an existing hand-written file, it never creates one from scratch here.",
                file=sys.stderr,
            )
            sys.exit(1)
        interfaces_code = _splice_generated_block(existing, spec, args.spec)
    else:
        interfaces_code = generate_interfaces(spec, args.spec)

    doc_md = generate_doc(spec, args.spec)

    out_interfaces.parent.mkdir(parents=True, exist_ok=True)
    out_interfaces.write_text(interfaces_code)
    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text(doc_md)
    print(f"Generated {out_interfaces}", file=sys.stderr)
    print(f"Generated {out_doc}", file=sys.stderr)


if __name__ == "__main__":
    main()
