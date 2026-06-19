SPHINXBUILD   ?= sphinx-build
SPHINXAPIDOC  ?= sphinx-apidoc
SOURCEDIR      = .
BUILDDIR       = _build

.PHONY: help html clean apidoc livehtml

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)"

# Re-generate RST stubs from source then build HTML.
# Run this whenever new modules are added.
html: apidoc
	@$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" -W --keep-going
	@echo
	@echo "Build finished → $(BUILDDIR)/html/index.html"

# Auto-generate per-module RST files.
# --force overwrites stale stubs; --module-first puts module docstring before submodule list.
apidoc:
	@$(SPHINXAPIDOC) \
		--output-dir api/backend/generated \
		--force \
		--module-first \
		--separate \
		../backend/src/chem_bench
	@$(SPHINXAPIDOC) \
		--output-dir api/frontend/generated \
		--force \
		--module-first \
		--separate \
		../frontend/src/chem_bench_ui

clean:
	rm -rf "$(BUILDDIR)"
	rm -rf api/backend/generated api/frontend/generated

# Live-reload dev server — requires sphinx-autobuild (pip install sphinx-autobuild)
livehtml: apidoc
	sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)/html" --open-browser
