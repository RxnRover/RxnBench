import os
import sys

# Both packages must be importable during autodoc
sys.path.insert(0, os.path.abspath("../backend/client/src"))
sys.path.insert(0, os.path.abspath("../frontend/src"))

project = "Automated Rxn Bench"
copyright = "2026, John Brittain"
author = "John Brittain"
release = "0.1"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

autosummary_generate = True

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "special-members": "__init__",
}

# Google-style and NumPy-style docstrings both supported
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Mock heavy/platform-specific packages so autodoc can import source files
# on any machine without requiring all runtime deps to be installed.
autodoc_mock_imports = [
    # Qt
    "PySide6",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtUiTools",
    # gRPC / protobuf / SiLA
    "grpc",
    "google",
    "google.protobuf",
    "google.protobuf.internal",
    "google.protobuf.descriptor",
    "google.protobuf.message",
    "google.protobuf.reflection",
    "sila2",
    "unitelabs",
    # compiled proto stubs in the source tree (can't load without the full runtime)
    "rxn_bench_ui.proto.sila_service_pb2",
    "rxn_bench_ui.devices.gantry.proto.motion_platform_pb2",
    # other deps
    "zeroconf",
    "yaml",
    "smbus2",
    "requests",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = "Automated Rxn Bench"

html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
}
