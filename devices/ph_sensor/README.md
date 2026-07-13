# pH Sensor

Reads pH from an Atlas Scientific EZO-pH circuit over I2C, with mid/low/high three-point calibration and a streaming `Ph` observable property.

- **`backend/`** — `rxn-bench-ph` SiLA2 server (port 50052), runs on the device host alongside `rxn-bench-gantry` (a Raspberry Pi in the reference deployment). See [backend/README.md](backend/README.md) for the full SiLA feature list, hardware wiring, calibration workflow, and how to swap in a different pH sensor.
- **`frontend/`** — the pH device plugin for the PySide6 UI (live reading graph, calibration controls, gRPC connection layer). Runs as part of `rxn_bench_ui` on the operator machine. See `frontend/__init__.py` for the `FEATURE_FRAGMENTS`/`create_widget` contract.

Both halves are independently deployable — the backend never runs on the operator machine, and the frontend never imports backend code directly (SiLA/gRPC only). See [docs/ai/CURRENT_STATE.md](../../docs/ai/CURRENT_STATE.md) for the full architecture.

Note: `backend/tests/` currently has no real test coverage (see `docs/ai/CURRENT_STATE.md` gaps) — `devices/gantry/backend/tests/` is the model to follow.
