# Gantry

The XYZ motion device: drives the Sovol SV08 gantry via Moonraker/Klipper, manages toolhead geometry, workspace/well-plate layout, and homing state.

- **`backend/`** — `rxn-bench-gantry` SiLA2 server (port 50051), runs on the Raspberry Pi. See [backend/README.md](backend/README.md) for the full SiLA feature list, configuration, hardware wiring, and how to add a toolhead or well plate.
- **`frontend/`** — the gantry device plugin for the PySide6 UI (widget, gRPC connection layer). Runs as part of `rxn_bench_ui` on the operator machine. See `frontend/__init__.py` for the `FEATURE_FRAGMENTS`/`create_widget` contract.

Both halves are independently deployable — the backend never runs on the operator machine, and the frontend never imports backend code directly (SiLA/gRPC only). See [docs/ai/CURRENT_STATE.md](../../docs/ai/CURRENT_STATE.md) for the full architecture.
