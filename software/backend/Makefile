.PHONY: install start-gantry start-ph start-mock test-gantry test-ph test gen-proto check-proto

FRONTEND_PROTO_DIR := ../../devices/gantry/frontend/proto
FRONTEND_PROTO     := $(FRONTEND_PROTO_DIR)/motion_platform.proto

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

# Position and ToolheadInfo dataclasses live in rxn_bench_gantry.feature.

gen-proto:
	uv run python $(GANTRY_DIR)/scripts/gen_proto.py > $(FRONTEND_PROTO)
	uv run python -m grpc_tools.protoc \
		-I $(FRONTEND_PROTO_DIR) \
		--python_out=$(FRONTEND_PROTO_DIR) \
		$(FRONTEND_PROTO)

check-proto:
	@uv run python $(GANTRY_DIR)/scripts/gen_proto.py | diff - $(FRONTEND_PROTO) \
		|| (echo "\nERROR: motion_platform.proto is out of date. Run 'make gen-proto'." && exit 1)
	@echo "OK: motion_platform.proto matches backend dataclasses."
