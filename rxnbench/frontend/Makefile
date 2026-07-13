.PHONY: gen-connections check-connections test dist dist-check

DEVICES_DIR := ../../devices

# Headless frontend tests (generator golden checks, error formatting, canvas
# geometry conversion - no display needed).
# PYTHONPATH is cleared to prevent ROS2 pytest plugins from interfering.
test:
	PYTHONPATH="" QT_QPA_PLATFORM=offscreen uv run pytest tests/ -v

# Regenerate every device's generated_connection.py from its connection_spec.yaml.
gen-connections:
	@for spec in $(DEVICES_DIR)/*/frontend/connection_spec.yaml; do \
		out=$$(dirname $$spec)/generated_connection.py; \
		uv run python scripts/gen_connections.py $$spec --out $$out; \
	done

# CI drift check: fail if any generated_connection.py is stale relative to its spec.
check-connections:
	@status=0; \
	for spec in $(DEVICES_DIR)/*/frontend/connection_spec.yaml; do \
		out=$$(dirname $$spec)/generated_connection.py; \
		uv run python scripts/gen_connections.py $$spec --out /tmp/_check_connection.py > /dev/null; \
		if ! diff -q /tmp/_check_connection.py $$out > /dev/null; then \
			echo "ERROR: $$out is out of date. Run 'make gen-connections'."; \
			status=1; \
		fi; \
	done; \
	rm -f /tmp/_check_connection.py; \
	if [ $$status -eq 0 ]; then echo "OK: all generated_connection.py files match their connection_spec.yaml."; fi; \
	exit $$status

# Build a standalone onedir executable (packaging/rxn-bench-ui.spec) and stage
# devices/*/frontend/ next to it, matching the drop-in plugin model.
# PyInstaller does not cross-compile: run this on the target OS (Windows for
# the required target) to get a native build.
dist:
	uv run --group package pyinstaller --noconfirm --distpath dist --workpath build packaging/rxn-bench-ui.spec
	uv run python packaging/copy_device_plugins.py dist/rxn-bench-ui

# Build-verification pass against the real frozen exe: actually constructs
# every discovered device widget (see packaging/entrypoint.py) rather than
# just starting the app, since a plugin's missing dependency only surfaces
# once something tries to load that plugin.
dist-check: dist
	cd dist/rxn-bench-ui && RXN_BENCH_UI_SELFTEST=1 QT_QPA_PLATFORM=offscreen ./rxn-bench-ui
