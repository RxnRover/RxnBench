"""Sphinx configuration for rxn-bench-ui."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

project   = "rxn-bench-ui"
author    = "Ames National Laboratory"
copyright = "2026, Ames National Laboratory"
release   = "0.1.2"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

napoleon_google_docstring  = True
napoleon_numpy_docstring   = False
napoleon_use_param         = True
napoleon_use_rtype         = True
napoleon_attr_annotations  = True

autodoc_member_order   = "bysource"
autodoc_typehints      = "description"
autodoc_default_options = {
    "members":          True,
    "undoc-members":    True,
    "show-inheritance": True,
}

autodoc_mock_imports = [
    # Qt
    "PySide6",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtUiTools",
    # gRPC / protobuf
    "grpc",
    "google",
    "google.protobuf",
    "google.protobuf.internal",
    "google.protobuf.descriptor",
    "google.protobuf.message",
    "google.protobuf.reflection",
    # compiled proto stubs in the source tree (can't load without the full runtime)
    "rxn_bench_ui.proto.sila_service_pb2",
    "rxn_bench_ui.devices.gantry.proto.motion_platform_pb2",
    "rxn_bench_ui.devices.ph_sensor.proto.ph_sensor_pb2",
    "rxn_bench_ui.devices.camera.proto.camera_pb2",
    "rxn_bench_ui.devices.dosing_pump.proto.dosing_pump_pb2",
    # other deps
    "zeroconf",
    "yaml",
    "rxn_bench_client",
]

# The gantry/ph_sensor frontend plugins live under devices/<name>/frontend/ and are
# loaded into the rxn_bench_ui.devices.<name> namespace at runtime by a custom importlib
# loader (rxn_bench_ui.devices.all_devices). autodoc never triggers that, so pre-register
# the plugin packages here - with the autodoc mocks active so their submodule imports
# resolve - otherwise autodoc can't import rxn_bench_ui.devices.<name>.* to document them.
from sphinx.ext.autodoc.mock import mock as _mock  # noqa: E402

with _mock(autodoc_mock_imports):
    try:
        from rxn_bench_ui import devices as _devices
        _devices.all_devices()
    except Exception as _exc:  # best-effort: never fail the docs build over a plugin
        print(f"[conf.py] device plugin preload skipped: {_exc}")

html_theme = "furo"
html_static_path = ["_static"]

exclude_patterns = ["_build"]
