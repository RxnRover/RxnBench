# Changelog

All notable changes to Rxn Bench are recorded here.

## [Unreleased]

### Fixed

- `client` (2026-08-06): `RxnBenchClient.close()` now parks a connected gantry (`save_and_park()`) before releasing the experiment lock unconditionally, whatever the reason the session is ending - normal script completion, a manual stop from the UI (`ExperimentStopped` propagating out of `check_pause_stop()`), or any unhandled exception. Previously this relied entirely on the script itself explicitly calling `bench.gantry.save_and_park()` at the end; a script killed mid-run (SIGINT from the Experiment Runner's Stop button, or a probe/motion failure) skipped it, leaving the gantry's saved homing state stale relative to wherever it actually stopped and requiring a manual re-home next session. `connect()` now tracks every wrapped instrument (not just the lock holder) so `close()` can find and park a connected gantry regardless of connection order; `save_and_park()` on a dead/nonexistent connection is swallowed so it can't strand the experiment lock. The explicit `bench.gantry.save_and_park()` call is no longer needed in scripts (removed from the usage examples in `client.py`/`instruments.py`) but calling it is still harmless.
- `client` (2026-08-06): `PHProbe.read_stable()` no longer raises `PHStabilityTimeout` (removed) when the probe fails to settle within `timeout` - it prints a warning with the best-effort reading (last valid value, final drift/range) and returns that instead. Previously an uncaught timeout on any single well or calibration point crashed the whole run (`pH_calibrate_and_sample.py`, `calibrate_ph.py`, and both tutorial scripts all called `read_stable()` without a `try`/`except`) and lost every well after it; now a slow-to-settle well just gets logged and the run continues. Also fixes `pH_calibrate_and_sample.py`'s sample-well log rows silently dropping `settling_time` (it wasn't in the explicit `columns=` list passed to `set_log_output`, so `csv.DictWriter`'s `extrasaction="ignore"` was discarding it).

### Changed

- `client` (2026-08-06): `Gantry.shake()` now alternates axes round-robin (`axis` default `"y"` -> `"xy"`) and uses more, smaller bursts (`amplitude` 2.0mm -> 1.5mm, `cycles` 10 -> 12) instead of one long oscillation on a single axis - shorter, more frequent direction reversals across more than one axis flings droplets off more effectively. `axis` still accepts any combination of `"x"`/`"y"`/`"z"` (a single letter reproduces the old single-axis behavior); no SiLA/backend changes, this is client-side motion-pattern only (the Jog command has no speed parameter to tune).

- `devices` (2026-08-05): all 5 device frontends (gantry, ph_sensor, camera, dosing_pump, device_template) restructured from a flat `devices/<name>/frontend/*.py` tree into a pip-installable `src/rxn_bench_<name>_frontend/` package declaring a `rxn_bench.devices` entry point, matching the `src/` layout backend device packages already use. `rxn_bench_ui/devices/__init__.py`'s `all_devices()` now merges entry-point discovery with the previous `devices/*/frontend/` directory scan (kept as a zero-rebuild drop-in fallback for devices not packaged as a formal dependency). Each of the 10 device folders (5 frontend, 5 backend) is now also its own git repo, wired in as a submodule (`.gitmodules`) — first step towards a master-repo layout for the JOSS publication. `.gitmodules` currently points at local repo paths pending GitHub hosting. PyInstaller packaging (`rxn-bench-ui.spec`) now bundles the 5 device packages' code and entry-point metadata (`collect_all` + `copy_metadata`) at build time instead of staging their folders next to the executable; CI checkout steps gained `submodules: true`. Verified end-to-end: all 5 widgets construct via entry points both in dev and inside a real PyInstaller-frozen build (`make dist-check`), full backend + frontend test suites pass, `make check-proto`/`make check-connections` are clean.
- `devices` (2026-08-05): each backend device further split into a **capability** package (`rxn_bench_<name>` - SiLA feature, Protocol interface, hardware-agnostic generic mock) and a **driver** package (`rxn_bench_<vendor>_driver` - concrete vendor implementation, wire-protocol mocks, hardware CAD, toolhead config), the latter registered under a new `rxn_bench.<name>_drivers` entry-point group so no capability imports a concrete driver directly - the backend mirror of the frontend's entry-points plugin split. `devices/<name>/{capability,driver}` are each their own git repo/submodule (9 total: all 4 real devices have both, device_template only has capability - no real driver to split out). New `rxnbench/backend/scripts/aggregate_toolheads.py` (wired into `make install`/`install_offline.sh`) copies each driver's toolhead config (e.g. the pH probe's mount/engage geometry) into gantry's bundled `toolheads/` directory at install time, since gantry doesn't own device-specific toolhead data but does need it in its own package to load. Also fixes `install_service.sh`, `build_offline_bundle.sh`, and both Makefiles' proto/connection-spec glob paths for the new nesting, and switches CI's backend job to `make install` (was a bare `uv sync`, silently skipping the toolhead aggregation). Verified end-to-end: full backend test suite (capability + driver tests, all 4 devices), `check-proto`, full frontend suite, `check-connections`, and a real PyInstaller-frozen build (`make dist-check`) constructing all 5 device widgets. Not re-verified: an actual offline-bundle build + from-scratch Pi install (see CURRENT_STATE.md gap).

## [v0.1.5] - 2026-08-05

Packaged install now ships example scripts and workspace templates, results logging no longer silently overwrites a previous run, and a new 24-well 5mL rack labware/workspace update.

### Added

- `frontend` (2026-08-05): packaging now stages `Scripts/` and `Workspaces/` folders next to the built executable (`packaging/copy_workflows.py`, mirroring the existing `copy_device_plugins.py` pattern) - `Scripts/` from `rxnbench/backend/client/scripts/`, `Workspaces/` from the gantry's `workspace/definitions/*.yaml`. The Experiment Runner's "Browse" dialog and the gantry plugin's "Import Workspace YAML" dialog both default to these folders (falling back to the equivalent source-tree paths in a dev checkout), so a fresh install ships ready-to-run examples instead of requiring an operator to find them in a source checkout. `Workspaces/` is explicitly import-and-edit examples, not live device config - the gantry backend loads named workspaces from its own copy on the bench Pi. Wired into both build paths (`make dist` and the CI Windows build, which invokes the packaging steps directly rather than via `make dist`).

### Changed

- `gantry` (2026-08-05): added `24_well_5ml` labware (24-well rack sized for 5ml vials, `well_depth_mm=60`) and switched the `3_24-well_wWash` workspace's three 24-well plates from `24_well_15ml` to it. `washing_station` well depth 45 -> 40mm and footprint `height_mm` 85.48 -> 93.58mm.

### Fixed

- `client` (2026-08-05): `RxnBenchClient.set_log_output()` no longer silently overwrites an existing results file with the same name - if the resolved path already exists, `_1`, `_2`, ... is appended to the filename stem until an unused one is found. A re-run of a script with the same log filename (e.g. `ph_sample.csv`) now produces `ph_sample_1.csv` instead of clobbering the previous run's data.

## [v0.1.4] - 2026-08-04

Dosing pump device added and verified against real hardware (UART smoke test + a fixed concurrency bug), gantry labware/rotation fixes for the new 24-well 15mL rack, and client-side logging resilience.

### Changed

- `client` (2026-07-24): reconditioned `PHProbe.read_stable` defaults so the stability gates are statistically sound for this probe's noise. `window` 5 → 10 and `max_range` 0.02 → 0.03. The OLS slope's standard error is `sigma/sqrt(sum (t-tbar)^2)`, ~0.0022 pH/s at window=5 vs ~0.0008 at window=10; with the probe's measured per-reading noise `sigma ~= 0.007 pH` (from `results/ph_traces`), window=5 put the slope SE *above* `max_drift=0.002`, so a settled probe failed the drift gate ~35% of windows on noise alone (erratic settle times / spurious timeouts). Peak-to-peak grows with window size (`E[ptp] ~= 3.1*sigma ~= 0.021` at window=10), so `max_range` was loosened to 0.03 to avoid rejecting settled windows. `_StabilityMonitor` math (OLS slope / ptp / window mean) was reviewed and is correct; only the defaults changed. `scripts/tune_endpoint.py` `EndpointConfig` updated to match, and its trace loader now tolerates truncated CSV rows (`float(None)` -> `TypeError` was uncaught). Note: re-tuning against the current traces still fails the accuracy bar because those samples barely settle — physical settling (submersion/mixing, longer `TRACE_SECONDS`) is the limiter, not the detector.
- `gantry` (2026-07-23): raised the `ph_probe` toolhead `z_engage` from 40 to 65 mm. Because `_effective_engage_depth` blends `z_engage` with each well's `well_depth_mm`, the switch of the 6-well holder from 50 mL (`well_depth 100`) to 25 mL tubes (`well_depth 77`) had silently reduced the probe's descent from ~70 mm to ~58.5 mm, leaving the junction insufficiently submerged and skewing readings. 65 restores ~71 mm in the 25 mL tubes and lets the `well_depth − engage_bottom_margin` cap govern the shallower calibration/wash wells (probe now seats ~2 mm above their bottoms). Deploy: sync `toolheads/` to the Pi + restart `rxn-bench-gantry`.
- `client` (2026-07-15): `PHProbe.read_stable` automatic endpoint detection instead of the "N consecutive readings within a tolerance band" check. Readings stream into a rolling window (`window`, default 5) and, once the window is full and at least `min_settle` s (default 5) have elapsed
- `gantry` (2026-07-15): tool engagement depth is now derived from the labware, not only the toolhead config. `GantryController._effective_engage_depth` blends the toolhead's configured `z_engage` with the docked well's own measured `well_depth_mm` (the mean of the two) and caps the result a fixed gap above the well bottom (`MachineConfig.engage_bottom_margin_mm`, new, default 2 mm). This *replaces* the previous hard rejection when `z_engage` exceeded a well's depth: a toolhead configured deeper than a shallower plate's wells — e.g. the bench `ph_probe`'s `z_engage=40` on a 36 mm-deep 96-well plate, which was being refused outright — now engages, capped, instead of blocking the move. The controller tracks the docked well `_current_well_label`, set by `move_to_well`.

### Added

- `dosing_pump` (2026-07-29): new device — Atlas Scientific **EZO-PMP** embedded peristaltic dosing pump as `rxn-bench-dosing-pump` on port 50054. Exposes all four datasheet dispensing modes (fixed volume `D,[ml]`, dose over time `D,[ml],[min]`, constant flow rate `DC,[ml/min],[min|*]`, continuous `D,*`) plus pause/stop/invert, single-point calibration, and net/absolute total-volume counters. Adds `devices/dosing_pump/{backend,frontend}`, the `DosingPump` SiLA feature, a `rxn_bench_client.DosingPump` instrument (with `dispense_and_wait()` for scripts that must block until liquid is actually delivered), and a Qt widget.

  The frontend plugin follows the **pH widget as its baseline**: a `ui/dosing_pump_widget.ui` loaded via `QUiLoader` with `findChild` lookups, one 44pt hero readout for dispensed volume, and a custom-painted `VolumeGraph` history trace injected into a placeholder. The graph auto-scales its Y axis (a dose can be 0.5 ml or 500 ml, unlike pH's fixed 0-14) and greys the trace while the pump is idle. A **mode combo** (Volume / Dose over time / Constant rate / Continuous) enables only the inputs each mode uses and relabels the action button, mirroring how the pH widget's calibration-point combo gates its value spin — this replaced a first pass that stacked six `QGroupBox`es with no `.ui` file and no graph. Note that setting *any* Qt stylesheet replaces the default disabled palette, so the mode-gated inputs, labels, and the Stop button each need explicit `:disabled` rules or they look active while disabled.

  A **new device rather than a reuse**: the pump is an actuator, and `DosingPumpProtocol` has no overlap with `PHSensorProtocol` (read/calibrate/slope), `CameraProtocol` (`capture()`), or the gantry's motion protocol. The Atlas EZO *UART wire protocol* is shared with `rxn_bench_ph` and is deliberately re-implemented rather than imported, per the per-device self-containment rule (`docs/ai/CURRENT_STATE.md` §8) — the shape is copied (transport-agnostic `EZOPumpCommandSet` + one transport class), not the code. Only UART is implemented; the command set stays transport-agnostic so the pump's I2C mode can be added later as a transport class.

  Two EZO-PMP protocol quirks the pH circuit doesn't have, both handled explicitly: `*DONE,<volume>` is *both* the only reply to `X` (stop) *and* an unsolicited interrupt whenever a dispense finishes on its own, so the driver accepts it as a reply only when the in-flight command expects one (`done_terminates`) and otherwise records it in `last_completed_volume` and skips it — without that, a dose completing during an unrelated query (e.g. `TV,?`) would silently return the dispensed volume as the total. And `*MINVOL` (below the 0.5 ml minimum) / `*TOOFAST` (above the calibrated max) are command rejections distinct from plain `*ER`, surfaced as `ValueError` naming the cause. The pump's two *toggle* commands (`P`, `Invert`) are wrapped as idempotent setters that read current state first, so scripts assert a state instead of tracking parity.

  `MockEZOPumpUart` emulates the protocol and *simulates dispensing against an injectable clock*, so the real driver stack runs without hardware and a dose actually progresses and completes over its requested duration (the mock server is genuinely drivable, not a constant-returning stub). 77 backend tests. Verified end-to-end against a live mock server over real gRPC — progressive dispensing, `Stop`'s float return, unobservable-property reads, error propagation — plus the real Qt widget constructed and driven headlessly.

  Driver-level circuit housekeeping (`find`, `set_led`/`get_led`, `sleep`/`wake`, `set_protocol_lock`/`get_protocol_lock`) is present on `EZOPumpCommandSet`/`AtlasDosingPump` but deliberately **not** exposed over SiLA, matching how `rxn_bench_ph` keeps the same group driver-level only. `sleep()` needs a paired `wake()`: the byte that wakes a sleeping EZO is consumed doing so and is *not* executed — the circuit answers `*WA` and the command is silently lost — so `wake()` absorbs that throwaway exchange (`MockEZOPumpUart` reproduces the swallow, so it's tested rather than assumed). Note `sleep()` only powers down the control system, not the 12–24 V motor supply. Not implemented on purpose: `Baud`/`Factory`/`Name`/I2C-switch (can strand the connection mid-run), `O` (changes the output string format `R` parsing depends on), and `Dstart` (runs the pump on power-up without a client).

  **Not yet run against physical hardware.** Two things to resolve first: the EZO-pH already owns the Pi's primary UART (`/dev/serial0`), so the pump needs its own port (`dtoverlay=uartN` or a USB-serial adapter, via `RXN_BENCH_PUMP_SERIAL_PORT`), and the pump requires **two** supplies — 3.3–5.5 V logic *and* 12–24 V motor; logic-only will look alive over UART but never turn the motor. See the new gaps in `CURRENT_STATE.md` §6.
- `dosing_pump` (2026-08-04): made the device reusable by a second pump model rather than welded to the EZO-PMP, per the minimally-viable-interface goal. Three changes, no wire-format break:
  - **`DosingPumpProtocol` trimmed to a 12-method core** every dosing pump can satisfy. The vendor-specific parts moved into opt-in `runtime_checkable` capability protocols: `SupportsCalibration`, `SupportsDirectionInvert` (a *persistent* flip is an EZO feature; most pumps just take a signed volume), and `SupportsDiagnostics` (`pump_voltage` is the EZO's `PV,?`; a syringe pump has no equivalent). The feature probes them with `isinstance` and rejects only those commands, naming what's missing, instead of throwing `AttributeError`. `GetCalibrationStatus`'s docs no longer present the EZO's 0/1/2/3 as universal — 0 is uncalibrated, non-zero is pump-defined.
  - **No model-specific numbers left in the widget.** It dropped a hardcoded `105.0` and the `.ui`'s 0.5 ml / 105 ml-min limits; the Rate ceiling comes from the server's `MaxFlowRate` at runtime and per-pump minimums are enforced by the device and surfaced as errors. Hardcoding one pump's limits into UI that's matched by *feature identifier* would have broken every other pump that reuses it.
  - **`server.py` gained a `_DRIVERS` registry** keyed by `RXN_BENCH_PUMP_DRIVER` (default `atlas_ezo_pmp`), so adding a model is one builder entry, not an edit to the hardcoded Atlas path.

  Net effect: a second pump = one driver class + one registry line. No new frontend code, proto, connection layer, or client class, because `rxn_bench_ui` matches plugins on the advertised SiLA feature identifier (`FEATURE_FRAGMENTS`), not on hardware. Covered by tests that assert a core-only fake pump satisfies `DosingPumpProtocol`, drives every dispensing command through the feature, and fails exactly the six unsupported-capability calls (96 backend tests, up from 88).
- `dosing_pump` (2026-08-04): first real-hardware verification. The bench Pi 5's `dtoverlay=uart2` (already present in `config.txt`) brings up UART2 on GPIO4/5 (TXD2/RXD2) as `/dev/ttyAMA2` — confirmed by pin function (`pinctrl get 4,5` → `a2`) and by talking to the physical EZO-PMP over it: `?I` returned `PMP,1.06`, `?STATUS` and `PV,?` both responded, and the motor supply read 11.99 V. `install_service.sh`'s device registry gained a per-device `env_vars` field (`Environment=` lines in the generated unit) so the `pump` service now gets `RXN_BENCH_PUMP_SERIAL_PORT=/dev/ttyAMA2` automatically instead of defaulting onto the pH probe's `/dev/serial0`. Only a UART smoke test (`?I`/`?STATUS`/`PV,?`) was run against real hardware — dispensing, calibration, and the `*DONE` mid-query interrupt path are still unverified on the physical pump; see `CURRENT_STATE.md` §6.
- `gen_proto.py` (2026-07-29): added an `Integer` SiLA primitive wrapper (`message Integer { int64 value = 1; }`, plus `int` in `_SILA_TYPE`), needed by the dosing pump's `GetCalibrationStatus`. Second generic generator addition after the camera's `Binary`; verified to decode correctly against a live server. Declaring it `Real` would have broken decoding outright — the CDK sends a varint for a Python `int`, not a fixed64.
- `ci.yml` (2026-07-29): added the missing `make test-camera` step alongside the new `make test-pump`. The camera backend suite existed and was runnable locally but was never actually run in CI, despite `CURRENT_STATE.md` claiming coverage.
- `instrument.py` added a `Gantry.shake()` method which oscillates the gantry N number of times over `amplitude`, this is useful for flinging off excess liquid or material on the toolheads
- `client` (2026-07-15): two scripts for empirically tuning the pH endpoint detector against real hardware. `scripts/record_ph_traces.py` parks the probe in each well and logs the full pH-vs-time trace (instead of stopping early). `scripts/tune_endpoint.py` replays the shipping `_StabilityMonitor` over those traces across a grid of thresholds and reports, per config, median settle time, endpoint error vs. the trace's equilibrium (tail average), and premature-stop / timeout rates — so `read_stable`'s defaults can be chosen from this probe's data rather than borrowed. It reuses the production detector (not a copy) and runs offline against built-in synthetic traces when no recorded ones are given.

### Fixed

- `dosing_pump` (2026-08-04): fixed a real race condition found while verifying the pump against physical hardware — the SiLA feature polls two observable properties (`VolumeDispensed`, `Dispensing`) concurrently at 1Hz, each dispatched to its own OS thread via `asyncio.to_thread`, and any in-flight `Dispense`/`Stop` call from a script joins them; all shared one `serial.Serial` port with nothing serializing access. Two threads' writes/reads interleaved on the wire, producing garbled replies on the real EZO-PMP (`ValueError: could not convert string to float: 'O'`, `'D,100,'`, `'OK?-.0,0*'`) — never seen against the mock because `rxn_bench_ph` (the only prior EZO device) exposes just one observable stream, so this is the first concurrent-access path in the codebase. `EZOPumpCommandSet` gained a `threading.Lock` and a `_transact(cmd)` helper that performs each command's send+read as one atomic exchange; every command method now goes through it instead of calling `_send_command`/`_read_response` separately. Verified fixed against the real pump: 30 concurrent calls across two threads (15× `read_volume_dispensed`, 15× `get_dispense_status`), zero errors. All 96 backend tests still pass.
- `gantry` (2026-08-04): fixed the new `24_well_15ml` labware's well grid not being centered on its own plate footprint. `a1_offset_x`/`a1_offset_y` had been set from a "4mm wall clearance + well radius" formula rather than measured, which didn't reconcile with the confirmed plate footprint (127.90 × 85.50 mm) and caliper-measured spacing (21.75/21.53 mm) — the last column/row's wells landed asymmetrically (up to 1.35mm past the right edge). Recalculated to `a1_offset_x=9.58`, `a1_offset_y=10.46`, centering the grid on the footprint per the CAD drawing's own origin.
- `gantry` (2026-08-04): added `Orientation.ROTATED_270` (a 90° **clockwise** rotation, `(dx,dy) -> (dy,-dx)`) alongside the existing `ROTATED_90` (counter-clockwise). The three `24_well_15ml` plates in the `3_24-well_wWash` workspace need the opposite rotation direction from what `ROTATED_90` provides — A1 was landing on the wrong side of the plate. Implemented identically in `workspace_manager.py` (backend) and `workspace_loader.py` (frontend canvas, via a shared `_apply_orientation` helper) so the deck rendering and the real motion math never diverge. 3 new backend tests mirror the existing `ROTATED_90` cases.
- `client` (2026-08-04): `RxnBenchClient.log()` now catches `OSError` around the actual file write (header/row/flush) and skips that row with a printed warning instead of raising — a logging hiccup (e.g. a results folder on a network share that drops) no longer takes down an otherwise-healthy experiment run. The "forgot to call `set_log_output()` first" `RuntimeError` still raises, since that's a real script bug. **Known gap, not fixed:** none of the underlying SiLA/gRPC calls (`bench.ph.read()`, `bench.gantry.move_to_well()`, etc.) have a deadline — `sila2`'s `SilaClient` builds its channel with plain `grpc.insecure_channel` and never passes a per-call `timeout`, so a genuinely dead connection (e.g. the operator machine's ethernet unplugged) still hangs a script indefinitely rather than erroring. See `CURRENT_STATE.md` §6 for the fix options (client-only keepalive bounds it to ~5 min; going faster requires touching all four device backends' server config).

## [v0.1.2]

An important milestone was reached, the entire system, `gantry`,`ph_sensor`,`client`,`frontend` was able to perform a script `calibrate_ph.py`
which automatically calibrates the pH probe. This is important and proves the viability/usability of the system for many more experiments to come.

### Current Issues

- Gantry positioning: gantry is accurate enough to reliability move to and engage/disengage in a 24 well-plate, however struggles with smaller 96-well
plates. We'll need to confirm and verify all measure inside the `labware/`, `workspace/`, and `toolhead/` `.yaml` config files to see if there is an
improvement.

### Added

- `ph_sensor`: Ability to set tempeature compoensation was added into the interface, SiLA feature, client `instrument.py`, and EZO drivers. 
- `docs/build_all_docs.sh` script which builds the sphinx / generates UML for the entire repo
- `clean-repo/SKILL.md`: agent skill which cleans the repo of redundant code, cleans up excessive inline comments, and simplifies project structure,
to avoid overly nested folders etc.

### Changed

- `instrument.py:288` pH probe `read_stable` now keeps a rolling window of the last samples readings and only returns once the whole window spans ≤ tolerance (max - min), instead of just the latest pair
- `server.py:43`: the default speed of `moonraker_client()` was increased from `3000` to `4000`: `moonraker_client(host, DEFAULT_SPEED=4000)`

### Fixed

- Doc generation
- `ph_sensor`: the ph sensor was having problems calibrating, a written script `calibrate_ph.py` was created, the fix was to decrease the tolerance
and increase the interval to gather a more stable reading, as well as ensuring the probe was fully submerged into the sample.
- `client.py`: default log location was changed to the `root/results/` directory of the running frontend application unless specified.
- frontend: the packaged app can now actually run experiment scripts. The PyInstaller spec never bundled `rxn_bench_client` (nor its `sila2` / `grpc_tools` dependencies) - scripts are loaded only dynamically via `runpy` when the Experiment Runner runs one, so PyInstaller's static analysis never saw them - and the frozen app threw `ModuleNotFoundError: No module named 'rxn_bench_client'` on the first script run. The spec now `collect_all`s `rxn_bench_client`, `sila2`, and `grpc_tools` (the last needed because sila2 compiles FDL to gRPC stubs at runtime, and its Cython `_protoc_compiler` imports `grpc_version` invisibly to static analysis), matching how device-plugin deps (`yaml`, `connections.base`) are already handled. Verified by running a script through the real frozen exe. (2026-07-14)

## [0.1.1] - 2026-07-13

### Added

- frontend: `windows-latest` GitHub Actions workflow that builds the Windows desktop installer, uploads it as an artifact, and attaches it to version-tag GitHub Releases (so the `.exe` can be produced from a Linux dev machine).
- gantry: the X-gantry crossbar is now drawn in the workspace X/Z and Y/Z side views (under "show more details").
- gantry: opt-in crossbar collision check - refuses a well move or tool engagement that would drive the crossbar into a taller plate sharing the carriage's Y-row. Needs crossbar measurements in `machine.yaml` to activate.
- gantry: configurable `deck_height_mm` workspace field for the shared deck/workplate thickness, separate from each plate's own mount height and footprint. Defaults to 0, so existing workspaces are unchanged.

### Changed

- gantry: bumped the Gantry SiLA feature from v0 to v1 (`edu.iastate.ames/rxnbench/Gantry/v1`), matching pH and Camera. Frontend and backend must be deployed together.
- gantry: moving between wells of the same plate now travels at that plate's own clearance height instead of the full-deck safe height, cutting raise/lower time on multi-well scans.

### Fixed

- gantry: corrected `test_controller.py` cases that hardcoded plate dimensions instead of deriving them from the labware YAML.

## [0.1.0] - 2026-07-13

### Added

- camera: new `rxn_bench_camera` SiLA device (port 50053) that streams the latest webcam frame from a Crowsnest stream, with an adjustable capture interval and image archiving. Adds a generic SiLA `Binary` wire type and `snapshot()` / `save_snapshot()` / `set_capture_interval()` on the client.
- gantry: multi-toolhead support - several heads can be mounted at once, each confirmed once and then switched between in software; moves refuse an unmounted or uncalibrated head, and both UI slots drive their own head.
- gantry: backend enforces the experiment lock on the wire - `AcquireExperimentLock` returns a token and motion/toolhead/workspace commands take an optional `Token`; the client attaches it automatically.
- gantry: `ForceReleaseExperimentLock` - tokenless recovery for a lock stranded by a killed script, wired into the UI banner and the client.
- gantry: `GetLabware` command serves all plate-geometry YAML as the single source of truth; deck canvases and the client fetch it instead of hardcoding grids.
- gantry: non-contact Z-reference calibration - the homing dialog and toolhead wizard can hover the tip at a known reference-plate height instead of touching a surface.
- gantry: new X/Z and Y/Z workspace side views alongside the top-down view, on both the Live and Configuration tabs, showing plate heights, the deck floor, safe-travel height, and per-well engagement depth.
- ph: UART/serial driver for the Atlas EZO-pH circuit (the bench probe is wired to the Pi's UART, not I2C), selected via `RXN_BENCH_PH_TRANSPORT`, sharing one EZO command set with the I2C driver plus a serial mock.
- client: `at_well()` gains an `override_unvalidated` passthrough so scripts can use a toolhead whose geometry is still placeholder.
- frontend: PyInstaller packaging groundwork - `make dist` builds a onedir app and stages each device plugin beside the executable; plugin discovery resolves `devices/` from the executable when frozen.
- frontend: closed the four gaps in the generic FDL-driven device widget - typed protobuf messages built from the FDL, typed command inputs with validation, and observable-command support - so it drives unknown SiLA2 devices without compiled stubs.
- backend: `install.sh` (shared uv workspace for dev) and `scripts/install_service.sh` (per-package venv plus the pH `rpi` extra) so each service deploys as its own systemd unit.
- docs: `new-device` dev-agent skill for scaffolding a device, requiring reuse of existing device interfaces before creating new ones.
- docs: top-level `devices/<name>/README.md` overviews for gantry, ph_sensor, and device_template.
- testing: first test suites for the pH backend, the client (37 tests), and the frontend (15 tests), plus the gantry suite extended to 133 tests.
- repo: GitHub Actions CI running both backend suites, the frontend suite, and both drift checks on push/PR.

### Changed

- repo: renamed the top-level `software/` folder to `rxnbench/` (`rxnbench/backend`, `rxnbench/frontend`) - path references updated and generated artifacts regenerated, no architecture change.
- repo: reorganized to a device-first layout - each device is a self-contained `devices/<name>/{backend,frontend}` folder.
- gantry: safe clearance-travel height is now derived from the loaded labware geometry (new `plate_height_mm`) instead of a flat 50 mm guess.
- ph: frontend connection uses generated protobuf stubs instead of hand-rolled varint helpers (also updated in `device_template`).
- frontend: gantry workspace loader now goes through `GantryConnection` instead of opening raw gRPC channels - closing the last plugin→core-internals boundary violation.
- backend: `gen_proto.py` generalized to a per-device manifest covering gantry, pH, and the template; adding a device's stubs is one entry.
- backend: offline-bundle default target Python is now 3.13 (the reference Pi's OS ships it); override with `PYTHON_VERSION`.
- docs: refreshed `CURRENT_STATE.md` - closed gaps removed, new stable decisions recorded.

### Fixed

- frontend: Experiment Runner now runs the selected script in packaged builds instead of relaunching the app.
- deployment: SiLA server discovery on the gatewayless bench network - servers now advertise the Pi's real IP over mDNS and a boot-time multicast route lets announcements reach the wire; `install_offline.sh` auto-detects and pins the host IP.
- gantry: `move_to_well` docks at the well's actual opening and rejects a move whose engage depth exceeds the well depth, instead of overshooting.
- gantry: lock-gated commands (`LoadWorkspaceYaml`, `Jog`, `MoveTo`, …) no longer fail with "Missing field Token" - the token arg is now declared for each, with a regression test cross-checking spec args against the proto.
- gantry: toolhead calibration wizard no longer rejects auto-moves against a plate shallower than the toolhead's configured engage depth.
- gantry: one broken labware file no longer breaks `GetLabware` for every plate - bad definitions are skipped with a warning and a clear error names the file.
- gantry: `GetWorkspaceYaml` and its subscription read from the controller's workspace manager, so workspaces loaded by name or restored at boot are visible to the stream and client.
- gantry: `MoonrakerClient` HTTP calls carry timeouts, so a wedged Moonraker no longer hangs a request while holding the hardware lock.
- gantry: fixed `motion_platform.proto` drift - the generator footer was missing the experiment-lock/pause/resume/stop RPCs.
- ph: fixed the real-hardware I2C path - new `SMBusI2C` adapter (passing `SMBus(1)` directly would have crashed) plus a mock I2C emulator for tests.
- frontend: packaged builds now bundle device-plugin dependencies (`collect_submodules`, `yaml`); `make dist-check` constructs every device widget in a frozen build to catch missing imports.
- frontend: connection layer now logs stream/command failures, closes channels on disconnect, and surfaces errors in the UI.
- backend: `make start-gantry` / `-ph` / `-camera` run fully offline from an extracted bundle; also fixed `start-ph` never installing the `rpi` extra (smbus2).
- backend: `install_offline.sh` persists the vendored `uv` on `PATH` so `make start-<device>` works right after install.
- backend: `build_offline_bundle.sh` - fixed requirements-file parsing (single-line exports), aarch64 wheel downloads (`manylinux2014_aarch64` tag), and the tar step pulling in its own output.
- backend: offline `install_service.sh` now bundles its build backend (`hatchling` / `editables`) so editable installs succeed with no network.
- docs: fixed `device_template/README.md`'s onboarding checklist (stale `sila_client.py` / `_FEATURE_REGISTRY` references and old spec paths).

### Removed

- gantry: dead-code sweep - unused sensor registry, an unconsumed signal, phantom widget fields, speculative generic SiLA fragments, and a phantom 384-well plate entry.
