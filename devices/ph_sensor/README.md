# pH Sensor

Streams pH readings with mid/low/high three-point calibration. Hardware-agnostic - the actual probe driver is separate, not baked in.

- **`capability/`** — the SiLA feature + PySide6 widget. `capability/backend/` is `rxn-bench-ph` (port 50052, runs on the device host alongside `rxn-bench-gantry` - a Raspberry Pi in the reference deployment). `capability/frontend/` is the pH device plugin (live reading graph, calibration controls). See [capability/backend/README.md](capability/backend/README.md) for the full SiLA feature list and calibration workflow.
- **`driver/`** — `rxn-bench-atlas-ezo-ph-driver`, the Atlas Scientific EZO-pH circuit driver (I2C or UART), plus the probe's toolhead mount CAD in `driver/hardware_models/` and its gantry toolhead config in `driver/toolhead/`. Swap this for a different pH probe's driver without touching the SiLA feature or widget. See [Supported-Devices.md](../../Supported-Devices.md).

`capability/backend/` and `driver/backend/` both only ever run on the device host; `capability/frontend/` only ever runs on the operator machine as part of `rxn_bench_ui` (SiLA/gRPC only, no direct imports). See [docs/ai/CURRENT_STATE.md](../../docs/ai/CURRENT_STATE.md) for the full architecture.
