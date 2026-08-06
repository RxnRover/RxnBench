"""Sphinx configuration for rxn-bench-dosing-pump."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

project   = "rxn-bench-dosing-pump"
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

autodoc_mock_imports = ["unitelabs"]

html_theme = "furo"
html_static_path = ["_static"]

exclude_patterns = ["_build"]
