# rxn-bench-atlas-ezo-ph-driver

The Atlas Scientific EZO-pH circuit driver, over either I2C or UART.

- `backend/` - `rxn_bench_atlas_ezo_ph_driver`, registered under the `rxn_bench.ph_drivers` entry-point group as `atlas_ezo`. Implements `PHSensorProtocol` from the capability package (`../capability/backend/`) - that's the only thing it depends on there. Transport is chosen at runtime with `RXN_BENCH_PH_TRANSPORT` (`i2c` default, or `uart`); see `build_sensor()` in `backend/src/rxn_bench_atlas_ezo_ph_driver/__init__.py` for the exact env vars.
- `hardware_models/` - the pH probe's toolhead mount CAD.
- `toolhead/ph_probe_toolhead.yaml` - the probe's gantry mount geometry (footprint, tip offsets, engage depth). This is data the gantry needs but doesn't own - `rxnbench/backend/scripts/aggregate_toolheads.py` copies it into the gantry capability's bundled `toolheads/` directory at install time. Edit it here, not the copy that shows up there.

This package is never imported directly by the capability - `rxn_bench_ph.server` discovers it (or any other registered pH driver) via `importlib.metadata.entry_points(group="rxn_bench.ph_drivers")`, selectable with `RXN_BENCH_PH_DRIVER` (default: `atlas_ezo`). See `../capability/backend/README.md` for how to run the server, and `.claude/CURRENT_STATE.md` §1 for the full capability/driver design.
