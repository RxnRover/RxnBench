.PHONY: install start-gantry start-ph start-mock test-gantry test-ph test gen-proto check-proto

# device-key:proto-stem pairs consumed by gen-proto/check-proto below.
# Keys must match _DEVICES in scripts/gen_proto.py; stubs land in
# devices/<key>/frontend/proto/<stem>.proto (+ compiled _pb2.py).
PROTO_DEVICES := gantry:motion_platform ph_sensor:ph_sensor device_template:my_device

GANTRY_DIR    := ../../devices/gantry/backend
PH_SENSOR_DIR := ../../devices/ph_sensor/backend

install:
	uv sync

start-gantry:
	cd $(GANTRY_DIR) && uv run rxn-bench-gantry

start-ph:
	cd $(PH_SENSOR_DIR) && uv run rxn-bench-ph

start-mock:
	RXN_BENCH_MOCK=1 uv run --package rxn-bench-gantry rxn-bench-gantry &
	RXN_BENCH_MOCK=1 uv run --package rxn-bench-ph rxn-bench-ph


# PYTHONPATH is cleared to prevent ROS2 pytest plugins from interfering.
test-gantry:
	PYTHONPATH="" uv run --package rxn-bench-gantry pytest $(GANTRY_DIR)/tests/ -v

test-ph:
	PYTHONPATH="" uv run --package rxn-bench-ph pytest $(PH_SENSOR_DIR)/tests/ -v

test: test-gantry test-ph

gen-proto:
	@for pair in $(PROTO_DEVICES); do \
		dev=$${pair%%:*}; stem=$${pair##*:}; \
		dir=../../devices/$$dev/frontend/proto; \
		mkdir -p $$dir; touch $$dir/__init__.py; \
		uv run python scripts/gen_proto.py $$dev > $$dir/$$stem.proto; \
		uv run python -m grpc_tools.protoc -I $$dir --python_out=$$dir $$dir/$$stem.proto; \
		echo "Generated $$dir/$$stem.proto (+ _pb2.py)"; \
	done

check-proto:
	@status=0; \
	for pair in $(PROTO_DEVICES); do \
		dev=$${pair%%:*}; stem=$${pair##*:}; \
		proto=../../devices/$$dev/frontend/proto/$$stem.proto; \
		if ! uv run python scripts/gen_proto.py $$dev | diff -q - $$proto > /dev/null 2>&1; then \
			echo "ERROR: $$proto is out of date. Run 'make gen-proto'."; \
			status=1; \
		fi; \
	done; \
	if [ $$status -eq 0 ]; then echo "OK: all frontend .proto files match their backend manifests."; fi; \
	exit $$status
