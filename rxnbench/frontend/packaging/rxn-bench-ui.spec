# PyInstaller spec for the Rxn Bench desktop UI.
#
# Produces a onedir build. Device frontend plugins (devices/<name>/frontend/)
# are intentionally NOT bundled here - rxn_bench_ui/devices/__init__.py loads
# them dynamically from a devices/ folder next to the built executable at
# runtime (see that file's docstring), so the shipped app stays a genuine
# drop-in plugin system rather than a fixed set baked in at build time.
#
# Build with: make dist   (from software/frontend/)
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

_SRC = os.path.join(SPECPATH, "..", "src")
# rxn_bench_client lives in a sibling package (backend/client/src) and is only
# imported by user experiment scripts, never by the UI - add its src to pathex
# so PyInstaller resolves it even though it's an editable install.
_CLIENT_SRC = os.path.join(SPECPATH, "..", "..", "backend", "client", "src")

# Device plugins import rxn_bench_ui.connections.base and pyyaml, but nothing
# on the statically-reachable import graph from entrypoint.py does - PyInstaller
# can't see those imports since plugin code is only ever loaded dynamically
# (see the spec's top comment), so they have to be listed explicitly or the
# frozen build throws ModuleNotFoundError the first time a plugin loads.
# collect_submodules("rxn_bench_ui") only walks the real installed package
# tree (software/frontend/src/rxn_bench_ui/), not devices/*/frontend/, so this
# stays consistent with keeping device plugin code out of the bundle.
_HIDDEN_IMPORTS = collect_submodules("rxn_bench_ui") + ["yaml"]

# The Experiment Runner runs user scripts inside this frozen bundle (see
# entrypoint._run_script), and those scripts import rxn_bench_client, which in
# turn imports sila2. Like the device plugins above, none of this is reachable
# from entrypoint.py's static import graph - scripts are only ever loaded
# dynamically via runpy at runtime - so both packages (plus sila2's data files)
# must be collected explicitly, or the runner throws ModuleNotFoundError the
# first time a script runs. grpc/zeroconf/yaml are already pulled in by the UI.
#
# sila2 compiles FDL into gRPC stubs at runtime via grpc_tools.protoc, so
# grpc_tools must be collected too. Its compiled _protoc_compiler extension does
# `from grpc_tools import grpc_version` internally - an import PyInstaller can't
# see inside a Cython .so - and needs the _proto/*.proto well-known types as
# data files, so a plain static analysis bundles the .so but leaves grpc_version
# and the protos out (ImportError: cannot import name grpc_version). There is no
# hooks-contrib hook for grpc_tools (only the grpc runtime), so collect it here.
_client_datas, _client_binaries, _client_hidden = collect_all("rxn_bench_client")
_sila_datas, _sila_binaries, _sila_hidden = collect_all("sila2")
_grpctools_datas, _grpctools_binaries, _grpctools_hidden = collect_all("grpc_tools")
_HIDDEN_IMPORTS += _client_hidden + _sila_hidden + _grpctools_hidden

a = Analysis(
    [os.path.join(SPECPATH, "entrypoint.py")],
    pathex=[_SRC, _CLIENT_SRC],
    binaries=_client_binaries + _sila_binaries + _grpctools_binaries,
    datas=[
        (os.path.join(_SRC, "rxn_bench_ui", "core", "ui"), os.path.join("rxn_bench_ui", "core", "ui")),
        (os.path.join(_SRC, "rxn_bench_ui", "assets"), os.path.join("rxn_bench_ui", "assets")),
    ]
    + _client_datas
    + _sila_datas
    + _grpctools_datas,
    hiddenimports=_HIDDEN_IMPORTS,
    hookspath=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Rxn Bench",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    # PyInstaller converts non-.ico images via Pillow (see `package` dep
    # group) and auto-generates the standard icon sizes from this source.
    icon=os.path.join(_SRC, "rxn_bench_ui", "assets", "rxnbench_logo.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Rxn Bench",
)
