# rxn-bench-crowsnest-camera-driver

Pulls still images from a Crowsnest-managed webcam stream over plain HTTP. Reference deployment: the Crowsnest instance running on the Sovol SV08's own controller.

- `backend/` - `rxn_bench_crowsnest_camera_driver`, registered under the `rxn_bench.camera_drivers` entry-point group as `crowsnest`. Implements `CameraProtocol` (one method: `capture() -> bytes`) - no dependency on the capability package at all, since Crowsnest's HTTP snapshot endpoint needs nothing from it.

This package is never imported directly by the capability - `rxn_bench_camera.server` discovers it (or any other registered camera driver) via `importlib.metadata.entry_points(group="rxn_bench.camera_drivers")`, selectable with `RXN_BENCH_CAMERA_DRIVER` (default: `crowsnest`). See `../capability/backend/README.md` for how to run the server and configure `crowsnest_base_url`/`crowsnest_snapshot_path`, and `.claude/CURRENT_STATE.md` §1 for the full capability/driver design.
