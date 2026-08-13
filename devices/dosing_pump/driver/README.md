# rxn-bench-atlas-ezo-pmp-driver

The Atlas Scientific EZO-PMP peristaltic pump driver, over UART.

- `backend/` - `rxn_bench_atlas_ezo_pmp_driver`, registered under the `rxn_bench.dosing_pump_drivers` entry-point group with **two** entries: `atlas_ezo_pmp` (real hardware) and `atlas_ezo_pmp_mock` (the `RXN_BENCH_MOCK=1` path). Implements `DosingPumpProtocol` from the capability package (`../capability/backend/`) - that's the only thing it depends on there.

The mock lives here rather than in the capability on purpose: `MockDosingPump` subclasses `AtlasDosingPump` and runs the real driver stack over a protocol emulator (`MockEZOPumpUart`) instead of stubbing the Protocol directly, so it exercises the same command encoding/timing the bench uses. That makes it genuinely driver-specific - see `backend/src/rxn_bench_atlas_ezo_pmp_driver/mock_device.py`.

This package is never imported directly by the capability - `rxn_bench_dosing_pump.server` discovers it (or any other registered pump driver) via `importlib.metadata.entry_points(group="rxn_bench.dosing_pump_drivers")`, selectable with `RXN_BENCH_PUMP_DRIVER` (default: `atlas_ezo_pmp`). See `../capability/backend/README.md` for the command set, wiring, and protocol notes, and `.claude/CURRENT_STATE.md` §1 for the full capability/driver design.
