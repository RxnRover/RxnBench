.PHONY: gen-connections check-connections

DEVICES_DIR := ../../devices

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
