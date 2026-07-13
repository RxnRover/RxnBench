# Camera

Streams periodic still images from a Crowsnest-managed webcam over SiLA. Initial target is the Crowsnest stream on the SOVOL SV08, but the hardware interface (`CameraProtocol`) only requires a `capture() -> bytes` method, so a different camera backend can be swapped in without touching the SiLA feature.

- **`backend/`** — `rxn-bench-camera` SiLA2 server (port 50053), runs on the device host alongside `rxn-bench-gantry`/`rxn-bench-ph` (a Raspberry Pi in the reference deployment, though the camera itself is attached to the SV08's own controller running Crowsnest). See [backend/README.md](backend/README.md) for the full SiLA feature list, Crowsnest wiring, and how to swap in a different camera source.
- **`frontend/`** — the Camera device plugin for the PySide6 UI (live image view, capture-interval control, gRPC connection layer). Runs as part of `rxn_bench_ui` on the operator machine. See `frontend/__init__.py` for the `FEATURE_FRAGMENTS`/`create_widget` contract.

Both halves are independently deployable — the backend never runs on the operator machine, and the frontend never imports backend code directly (SiLA/gRPC only). See [docs/ai/CURRENT_STATE.md](../../docs/ai/CURRENT_STATE.md) for the full architecture.
