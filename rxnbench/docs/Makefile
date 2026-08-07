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
	@echo "Build finished -> $(BUILDDIR)/html/index.html"

# Auto-generate per-module RST files.
# --force overwrites stale stubs; --module-first puts module docstring before submodule list.
# --no-toc skips the master modules.rst (index.rst drives the toctree via autosummary instead).
# Compiled *_pb2 proto stubs are excluded: they're mock-imported and carry no useful docs.
apidoc:
	@$(SPHINXAPIDOC) \
		--output-dir api/backend/generated \
		--force \
		--no-toc \
		--module-first \
		--separate \
		../backend/client/src/rxn_bench_client
	@$(SPHINXAPIDOC) \
		--output-dir api/frontend/generated \
		--force \
		--no-toc \
		--module-first \
		--separate \
		../frontend/src/rxn_bench_ui \
		"../frontend/src/rxn_bench_ui/proto/*_pb2.py" \
		"../frontend/src/rxn_bench_ui/devices/gantry/proto/*_pb2.py"

clean:
	rm -rf "$(BUILDDIR)"
	rm -rf api/backend/generated api/frontend/generated

# Live-reload dev server - requires sphinx-autobuild (pip install sphinx-autobuild)
livehtml: apidoc
	sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)/html" --open-browser
