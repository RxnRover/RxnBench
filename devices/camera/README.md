# Camera

Streams periodic still images over SiLA. `CameraProtocol` only requires a `capture() -> bytes` method, so the capability doesn't care what's behind it.

- **`capability/`** - the SiLA feature + PySide6 widget. `capability/backend/` is `rxn-bench-camera` (port 50053, runs on the device host alongside `rxn-bench-gantry`/`rxn-bench-ph` - a Raspberry Pi in the reference deployment). `capability/frontend/` is the Camera device plugin (live image view, capture-interval control). See [capability/backend/README.md](capability/backend/README.md) for the full SiLA feature list.
- **`driver/`** - `rxn-bench-crowsnest-camera-driver`, which pulls stills from a Crowsnest-managed webcam over HTTP (initial target: the Crowsnest stream on the SOVOL SV08's own controller). Swap this for a different camera source's driver without touching the SiLA feature or widget. See [Supported-Devices.md](../../Supported-Devices.md).

`capability/backend/` and `driver/backend/` both only ever run on the device host; `capability/frontend/` only ever runs on the operator machine as part of `rxn_bench_ui` (SiLA/gRPC only, no direct imports). See [docs/ai/CURRENT_STATE.md](../../docs/ai/CURRENT_STATE.md) for the full architecture.
