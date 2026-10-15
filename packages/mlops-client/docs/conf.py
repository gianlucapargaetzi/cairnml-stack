"""Sphinx configuration for the mlops-client documentation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mlops import __version__  # noqa: E402

project = "mlops-client"
author = "Gianluca Pargaetzi"
version = release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

# Docstrings are Google style (Args:, Returns:, Raises:).
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_param = True
napoleon_use_rtype = False

# Members are listed per directive in api.rst, so only what is documented there appears.
autodoc_default_options = {
    "show-inheritance": True,
}
autodoc_typehints = "description"

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "shibuya"
html_title = f"mlops-client {release}"
html_static_path = ["_static"]
