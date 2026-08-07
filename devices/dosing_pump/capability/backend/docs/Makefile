SPHINXBUILD   = sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build
PACKAGE       = rxn_bench_dosing_pump
SRCDIR        = ../src/$(PACKAGE)
UMLDIR        = _uml

.PHONY: help html uml clean

help:
	@echo "Usage:"
	@echo "  make html   - build HTML documentation"
	@echo "  make uml    - generate class/package UML diagrams (requires pylint)"
	@echo "  make clean  - remove build artifacts"

html:
	$(SPHINXBUILD) -b html $(SOURCEDIR) $(BUILDDIR)/html
	@echo "HTML docs written to $(BUILDDIR)/html/index.html"

uml:
	@command -v pyreverse >/dev/null 2>&1 || { echo "pyreverse not found. Run: pip install pylint"; exit 1; }
	mkdir -p $(UMLDIR)
	cd $(UMLDIR) && pyreverse -o png -p $(PACKAGE) ../$(SRCDIR)
	@echo "UML diagrams written to $(UMLDIR)/"
	@ls -1 $(UMLDIR)/*.png 2>/dev/null || true

clean:
	rm -rf $(BUILDDIR) $(UMLDIR)
