"""Sphinx configuration for rxn-bench-ui."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

project   = "rxn-bench-ui"
author    = "Ames National Laboratory"
copyright = "2026, Ames National Laboratory"
release   = "0.1.0"

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
    "rxn_bench_ui.proto.motion_platform_pb2",
    # other deps
    "zeroconf",
    "yaml",
    "rxn_bench_client",
]

html_theme = "furo"
html_static_path = ["_static"]

exclude_patterns = ["_build"]
