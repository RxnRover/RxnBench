.PHONY: install start stop install-service check-proto gen-proto test

install:
	bash install.sh

start:
	uv run chem-bench

install-service:
	bash scripts/install_service.sh

# Regenerate motion_platform.proto from backend dataclasses and recompile.
# Run this after any change to Position or ToolheadInfo field order.
PROTO_FILE := ../frontend/src/chem_bench_ui/proto/motion_platform.proto
PB2_FILE   := ../frontend/src/chem_bench_ui/proto/motion_platform_pb2.py

gen-proto:
	uv run python scripts/gen_proto.py > $(PROTO_FILE)
	uv run python -m grpc_tools.protoc \
		-I ../frontend/src/chem_bench_ui/proto \
		--python_out=../frontend/src/chem_bench_ui/proto \
		$(PROTO_FILE)

# Run smoke tests. PYTHONPATH is cleared to prevent ROS2 pytest plugins
# (registered in the system Python's entry_points) from interfering.
test:
	PYTHONPATH="" uv run pytest tests/ -v

# Fail CI if the committed .proto is out of date with the backend dataclasses.
check-proto:
	@uv run python scripts/gen_proto.py | diff - $(PROTO_FILE) \
		|| (echo "\nERROR: motion_platform.proto is out of date. Run 'make gen-proto'." && exit 1)
	@echo "OK: motion_platform.proto matches backend dataclasses."
