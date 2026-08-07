# rxn-bench-moonraker-driver

The gantry's motion driver: talks to Moonraker (Klipper's REST API) to actually move the XYZ carriage. Reference hardware: a Sovol SV08 3D printer.

- `backend/` - `rxn_bench_moonraker_driver`, registered under the `rxn_bench.gantry_drivers` entry-point group as `moonraker`. Implements `MotionClientProtocol` from the capability package (`../capability/backend/`) - that's the only thing it depends on there.
- `hardware_models/` - SV08 mounting brackets, belt clamps, and other platform-specific 3D-printable parts.

This package is never imported directly by the capability - `rxn_bench_gantry.server` discovers it (or any other registered gantry driver) via `importlib.metadata.entry_points(group="rxn_bench.gantry_drivers")`, selectable with `RXN_BENCH_GANTRY_DRIVER` (default: `moonraker`). See `../capability/backend/README.md` for how to run the server, and `docs/ai/CURRENT_STATE.md` §1 for the full capability/driver design.
