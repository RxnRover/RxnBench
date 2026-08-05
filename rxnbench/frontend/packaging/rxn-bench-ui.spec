# PyInstaller spec for the Rxn Bench desktop UI.
#
# Produces a onedir build. The five first-party device frontend plugins
# (gantry, ph_sensor, camera, dosing_pump, device_template) are now real
# installed dependencies of rxn-bench-ui (each its own package/repo, declaring
# a "rxn_bench.devices" entry point - see rxn_bench_ui/devices/__init__.py)
# rather than a devices/ folder copied next to the exe, so they're baked into
# the bundle at build time below. Adding one of these five to a build now
# requires a rebuild, not just dropping a folder next to the exe - the
# devices/*/frontend/ directory-scan fallback in rxn_bench_ui/devices/__init__.py
# still exists for that zero-rebuild drop-in case (e.g. an experimental device
# not yet packaged as a formal dependency), and copy_device_plugins.py still
# stages any such folders next to the executable.
#
# Build with: make dist   (from software/frontend/)
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

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
# stays consistent with keeping ad-hoc, non-packaged device plugin code out of
# the bundle - the five first-party device packages are collected explicitly
# below instead.
_HIDDEN_IMPORTS = collect_submodules("rxn_bench_ui") + ["yaml"]

# The five first-party device packages are only ever reached at runtime via
# importlib.metadata.entry_points() (see all_devices()), which is invisible to
# PyInstaller's static analysis just like the dynamic imports above - so their
# code needs collect_submodules/collect_all, same as everything else here.
# entry_points() itself works by scanning *.dist-info metadata on sys.path,
# which collect_all does NOT bundle (that's a separate PyInstaller concept) -
# copy_metadata() is required too, or the frozen build finds zero entry points
# and silently shows no devices at all.
_DEVICE_PACKAGES = [
    ("rxn_bench_gantry_frontend", "rxn-bench-gantry-frontend"),
    ("rxn_bench_ph_sensor_frontend", "rxn-bench-ph-sensor-frontend"),
    ("rxn_bench_camera_frontend", "rxn-bench-camera-frontend"),
    ("rxn_bench_dosing_pump_frontend", "rxn-bench-dosing-pump-frontend"),
    ("rxn_bench_device_template_frontend", "rxn-bench-device-template-frontend"),
]
_device_datas, _device_binaries, _device_hidden = [], [], []
for _import_name, _dist_name in _DEVICE_PACKAGES:
    _d, _b, _h = collect_all(_import_name)
    _device_datas += _d
    _device_binaries += _b
    _device_hidden += _h
    _device_datas += copy_metadata(_dist_name)
_HIDDEN_IMPORTS += _device_hidden

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
    binaries=_client_binaries + _sila_binaries + _grpctools_binaries + _device_binaries,
    datas=[
        (os.path.join(_SRC, "rxn_bench_ui", "core", "ui"), os.path.join("rxn_bench_ui", "core", "ui")),
        (os.path.join(_SRC, "rxn_bench_ui", "assets"), os.path.join("rxn_bench_ui", "assets")),
    ]
    + _client_datas
    + _sila_datas
    + _grpctools_datas
    + _device_datas,
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
