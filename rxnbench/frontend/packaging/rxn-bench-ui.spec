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

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

_SRC = os.path.join(SPECPATH, "..", "src")

# Device plugins import rxn_bench_ui.connections.base and pyyaml, but nothing
# on the statically-reachable import graph from entrypoint.py does - PyInstaller
# can't see those imports since plugin code is only ever loaded dynamically
# (see the spec's top comment), so they have to be listed explicitly or the
# frozen build throws ModuleNotFoundError the first time a plugin loads.
# collect_submodules("rxn_bench_ui") only walks the real installed package
# tree (software/frontend/src/rxn_bench_ui/), not devices/*/frontend/, so this
# stays consistent with keeping device plugin code out of the bundle.
_HIDDEN_IMPORTS = collect_submodules("rxn_bench_ui") + ["yaml"]

a = Analysis(
    [os.path.join(SPECPATH, "entrypoint.py")],
    pathex=[_SRC],
    datas=[
        (os.path.join(_SRC, "rxn_bench_ui", "core", "ui"), os.path.join("rxn_bench_ui", "core", "ui")),
        (os.path.join(_SRC, "rxn_bench_ui", "assets"), os.path.join("rxn_bench_ui", "assets")),
    ],
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
