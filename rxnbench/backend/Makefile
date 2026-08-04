.PHONY: install start-gantry start-ph start-camera start-pump start-mock test-gantry test-ph test-camera test-pump test-client test gen-proto check-proto

# device-key:proto-stem pairs consumed by gen-proto/check-proto below.
# Keys must match _DEVICES in scripts/gen_proto.py; stubs land in
# devices/<key>/frontend/proto/<stem>.proto (+ compiled _pb2.py).
PROTO_DEVICES := gantry:motion_platform ph_sensor:ph_sensor device_template:my_device camera:camera dosing_pump:dosing_pump

GANTRY_DIR    := ../../devices/gantry/backend
PH_SENSOR_DIR := ../../devices/ph_sensor/backend
CAMERA_DIR    := ../../devices/camera/backend
PUMP_DIR      := ../../devices/dosing_pump/backend

# Set only when running from inside an extracted build_offline_bundle.sh
# tarball, which ships a wheelhouse/ at its root (sibling to devices/,
# rxnbench/)
WHEELHOUSE := $(abspath ../../wheelhouse)

install:
	uv sync

start-gantry:
	@if [ -d "$(WHEELHOUSE)" ]; then \
		uv venv --no-project $(GANTRY_DIR)/.venv --allow-existing && \
		uv pip install --python $(GANTRY_DIR)/.venv/bin/python --no-index --find-links $(WHEELHOUSE) -e $(GANTRY_DIR) && \
		$(GANTRY_DIR)/.venv/bin/rxn-bench-gantry; \
	else \
		cd $(GANTRY_DIR) && uv run rxn-bench-gantry; \
	fi

start-ph:
	@if [ -d "$(WHEELHOUSE)" ]; then \
		uv venv --no-project $(PH_SENSOR_DIR)/.venv --allow-existing && \
		uv pip install --python $(PH_SENSOR_DIR)/.venv/bin/python --no-index --find-links $(WHEELHOUSE) -e "$(PH_SENSOR_DIR)[rpi]" && \
		$(PH_SENSOR_DIR)/.venv/bin/rxn-bench-ph; \
	else \
		cd $(PH_SENSOR_DIR) && uv run --extra rpi rxn-bench-ph; \
	fi

start-camera:
	@if [ -d "$(WHEELHOUSE)" ]; then \
		uv venv --no-project $(CAMERA_DIR)/.venv --allow-existing && \
		uv pip install --python $(CAMERA_DIR)/.venv/bin/python --no-index --find-links $(WHEELHOUSE) -e $(CAMERA_DIR) && \
		$(CAMERA_DIR)/.venv/bin/rxn-bench-camera; \
	else \
		cd $(CAMERA_DIR) && uv run rxn-bench-camera; \
	fi

start-pump:
	@if [ -d "$(WHEELHOUSE)" ]; then \
		uv venv --no-project $(PUMP_DIR)/.venv --allow-existing && \
		uv pip install --python $(PUMP_DIR)/.venv/bin/python --no-index --find-links $(WHEELHOUSE) -e "$(PUMP_DIR)[rpi]" && \
		$(PUMP_DIR)/.venv/bin/rxn-bench-dosing-pump; \
	else \
		cd $(PUMP_DIR) && uv run --extra rpi rxn-bench-dosing-pump; \
	fi

start-mock:
	RXN_BENCH_MOCK=1 uv run --package rxn-bench-gantry rxn-bench-gantry &
	RXN_BENCH_MOCK=1 uv run --package rxn-bench-ph rxn-bench-ph &
	RXN_BENCH_MOCK=1 uv run --package rxn-bench-dosing-pump rxn-bench-dosing-pump &
	RXN_BENCH_MOCK=1 uv run --package rxn-bench-camera rxn-bench-camera


# PYTHONPATH is cleared to prevent ROS2 pytest plugins from interfering.
test-gantry:
	PYTHONPATH="" uv run --package rxn-bench-gantry pytest $(GANTRY_DIR)/tests/ -v

test-ph:
	PYTHONPATH="" uv run --package rxn-bench-ph pytest $(PH_SENSOR_DIR)/tests/ -v

test-camera:
	PYTHONPATH="" uv run --package rxn-bench-camera pytest $(CAMERA_DIR)/tests/ -v

test-pump:
	PYTHONPATH="" uv run --package rxn-bench-dosing-pump pytest $(PUMP_DIR)/tests/ -v

test-client:
	PYTHONPATH="" uv run --package rxn-bench-client pytest client/tests/ -v

test: test-gantry test-ph test-camera test-pump test-client

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
