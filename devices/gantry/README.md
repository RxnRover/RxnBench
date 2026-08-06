# Gantry

The XYZ motion device: manages toolhead geometry, workspace/well-plate layout, and homing state. Hardware-agnostic - the actual motion controller is a driver, not baked in.

- **`capability/`** — the SiLA feature + PySide6 widget. `capability/backend/` is `rxn-bench-gantry` (port 50051, runs on the device host - a Raspberry Pi in the reference deployment). `capability/frontend/` is the gantry device plugin. See [capability/backend/README.md](capability/backend/README.md) for the full SiLA feature list, configuration, and how to add a toolhead or well plate.
- **`driver/`** — `rxn-bench-moonraker-driver`, the Moonraker/Klipper motion controller code (reference hardware: Sovol SV08 3D printer), plus its mounting-hardware CAD in `driver/hardware_models/`. This is what makes the gantry move; swap it for a different motion controller's driver without touching the SiLA feature or widget. See [Supported-Devices.md](../../Supported-Devices.md).

`capability/backend/` and `driver/backend/` both only ever run on the device host; `capability/frontend/` only ever runs on the operator machine as part of `rxn_bench_ui` (SiLA/gRPC only, no direct imports). See [docs/ai/CURRENT_STATE.md](../../docs/ai/CURRENT_STATE.md) for the full architecture.
