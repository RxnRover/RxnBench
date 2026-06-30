.PHONY: install start-gantry start-ph start-mock test-gantry test-ph test gen-proto check-proto

FRONTEND_PROTO_DIR := ../frontend/src/chem_bench_ui/proto
FRONTEND_PROTO     := $(FRONTEND_PROTO_DIR)/motion_platform.proto
CLIENT_PROTO_DIR   := client/src/chem_bench_client/proto

install:
	uv sync

start-gantry:
	cd gantry && uv run chem-bench-gantry

start-ph:
	cd ph_sensor && uv run chem-bench-ph

start-mock:
	CHEM_BENCH_MOCK=1 uv run --package chem-bench-gantry chem-bench-gantry &
	CHEM_BENCH_MOCK=1 uv run --package chem-bench-ph chem-bench-ph


# PYTHONPATH is cleared to prevent ROS2 pytest plugins from interfering.
test-gantry:
	PYTHONPATH="" uv run --package chem-bench-gantry pytest gantry/tests/ -v

test-ph:
	PYTHONPATH="" uv run --package chem-bench-ph pytest ph_sensor/tests/ -v

test: test-gantry test-ph

# Position and ToolheadInfo dataclasses live in chem_bench_gantry.feature.

gen-proto:
	uv run python gantry/scripts/gen_proto.py > $(FRONTEND_PROTO)
	uv run python -m grpc_tools.protoc \
		-I $(FRONTEND_PROTO_DIR) \
		--python_out=$(FRONTEND_PROTO_DIR) \
		$(FRONTEND_PROTO)
	cp $(FRONTEND_PROTO_DIR)/motion_platform_pb2.py $(CLIENT_PROTO_DIR)/

check-proto:
	@uv run python gantry/scripts/gen_proto.py | diff - $(FRONTEND_PROTO) \
		|| (echo "\nERROR: motion_platform.proto is out of date. Run 'make gen-proto'." && exit 1)
	@echo "OK: motion_platform.proto matches backend dataclasses."
