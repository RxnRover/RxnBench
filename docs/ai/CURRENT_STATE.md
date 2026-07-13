# Rxn Bench — Current State

**Last cleaned:** July 2, 2026  
**Purpose:** Keep the active architecture, current gaps, and next engineering moves visible without preserving every historical migration note.

---

## 1. Architecture Snapshot

Rxn Bench is a modular lab automation stack built around separate SiLA device servers and a PySide6 operator UI.

```text
Operator Machine
└── rxn_bench_ui  ── gRPC/SiLA ── Device Host (Raspberry Pi in the reference deployment)
    ├── core shell              ├── rxn-bench-gantry :50051 ── Moonraker/Klipper motion platform
    ├── device plugins          ├── rxn-bench-ph     :50052 ── pH sensor stack
    └── experiment scripts      └── rxn-bench-camera :50053 ── Crowsnest webcam stream
        └── rxn_bench_client
```

The backend is split into independently deployable packages:

| Package | Role | Notes |
|---|---|---|
| `rxn_bench_gantry` | Gantry SiLA server | Motion, homing, workspace/well movement, toolhead management, Moonraker bridge |
| `rxn_bench_ph` | pH SiLA server | pH readings, calibration, slope reporting, mock pH path |
| `rxn_bench_camera` | Camera SiLA server | Periodic image capture/streaming and archiving, Crowsnest HTTP bridge, mock camera path |
| `rxn_bench_client` | Experiment script client | Script-friendly session manager and instrument wrappers |
| `rxn_bench_template` | Device template | Reference package for adding future device servers |

The frontend is a PySide6 app with a stable split between core shell code and per-device plugins.

Per-package class/package UML diagrams (generated via `make uml`, see each package's `docs/Makefile`) are checked in at [docs/architecture/uml/](../architecture/uml/).

### Device-first layout

Each device is a self-contained top-level folder, not split across the `rxnbench/backend` and `rxnbench/frontend` trees:

```text
devices/
├── gantry/
│   ├── backend/    ← rxn_bench_gantry SiLA server package
│   └── frontend/   ← gantry device plugin (widget + connection layer)
├── ph_sensor/
│   ├── backend/    ← rxn_bench_ph SiLA server package
│   └── frontend/   ← pH device plugin
├── camera/
│   ├── backend/    ← rxn_bench_camera SiLA server package
│   └── frontend/   ← camera device plugin
└── device_template/
    ├── backend/    ← reference backend package for new devices
    └── frontend/   ← reference frontend plugin for new devices
```

This is a file-layout convention only — it does **not** relax the hard machine-separation rule below. `devices/<name>/backend/` still only ships to the device host (a Raspberry Pi in the reference deployment); `devices/<name>/frontend/` still only runs on the operator machine as part of the single `rxn_bench_ui` app; nothing under `frontend/` imports anything under `backend/`. `rxnbench/backend/` (uv workspace root, `client/`, `install.sh`) and `rxnbench/frontend/` (the app itself: `core/`, `connections/`, `proto/`) hold the code that isn't specific to one device.

---

## 2. Frontend Layout

```text
rxnbench/frontend/src/rxn_bench_ui/
├── app.py
├── discovery.py
├── themes.py
├── proto/
│   └── sila_service_pb2.py   ← shared SiLA framework stub only; device protos live with their device
├── connections/
│   └── base.py
├── core/
│   ├── main_window.py
│   ├── server_browser.py
│   ├── device_registry.py
│   ├── csv_viewer.py
│   ├── experiment_notes.py
│   └── generic_device.py
└── devices/
    └── __init__.py   ← loader only; scans repo-root devices/*/frontend/ (see below)
```

Each device's actual plugin code lives outside this tree, at the repo root:

```text
devices/gantry/frontend/
├── __init__.py
├── connection_spec.yaml
├── generated_connection.py
├── connection.py
├── widget.py
├── workspace_loader.py
├── experiment_panel.py
├── homing_dialog.py
├── toolhead_calibration_dialog.py
├── proto/
│   ├── motion_platform.proto
│   └── motion_platform_pb2.py
├── assets/
└── ui/

devices/ph_sensor/frontend/
├── __init__.py
├── connection_spec.yaml
├── generated_connection.py
├── connection.py
├── widget.py
├── proto/
│   ├── ph_sensor.proto
│   └── ph_sensor_pb2.py
└── ui/

devices/camera/frontend/
├── __init__.py
├── connection_spec.yaml
├── generated_connection.py
├── connection.py
├── widget.py
└── proto/
    ├── camera.proto
    └── camera_pb2.py
```

`devices/device_template/frontend/` mirrors the same shape, including its own
`proto/my_device{.proto,_pb2.py}` stubs, so the template teaches the compiled-stub
pattern end-to-end (the hand-rolled varint helpers it used to demonstrate are gone).

### Frontend rule

Each device plugin owns its own widget and connection layer. Core only handles application shell behavior, discovery, device selection, workspace tabs, theme propagation, and generic fallback UI.

### Device plugin contract

Each device's `devices/<name>/frontend/__init__.py` exports:

```python
FEATURE_FRAGMENTS: list[str]
def create_widget(server, theme: dict) -> QWidget: ...
```

`rxn_bench_ui/devices/__init__.py`'s `all_devices()` discovers plugins dynamically by scanning `devices/*/frontend/` and loading each `__init__.py` as `rxn_bench_ui.devices.<name>` via `importlib.util.spec_from_file_location` (so their relative imports, e.g. `from ...discovery import ...`, resolve normally). `core/device_registry.py` just calls `all_devices()`. Adding a new frontend device should not require editing the core registry. The scanned `devices/` directory itself resolves differently depending on how the app is running: in a source checkout it's the repo-root folder five levels up from `devices/__init__.py`; in a PyInstaller build (`sys.frozen`) it's a `devices/` folder expected to sit next to the built executable instead, so the same drop-in model holds after packaging — see "Standalone executable packaging" below.

### Standalone executable packaging

`rxnbench/frontend/packaging/` holds a PyInstaller setup (`rxn-bench-ui.spec`, `entrypoint.py`) that produces a onedir build of the app. `make dist` (in `rxnbench/frontend/`) runs PyInstaller and then `packaging/copy_device_plugins.py`, which stages every `devices/<name>/frontend/` (minus `backend/` and `__pycache__`) into a `devices/` folder next to the built executable. PyInstaller's static analysis never sees `devices/*/frontend/` — that's intentional, matching the dynamic-loading discovery above: device plugins are runtime data, not bundled code, so a deployed install stays extensible by dropping a new `devices/<name>/frontend/` folder next to the executable, no rebuild required. `.ui` files and `assets/` under `rxn_bench_ui/core/` are bundled explicitly as PyInstaller `datas` (not picked up by static analysis since they're loaded at runtime via `QUiLoader`/`Path(__file__).parent`).

Because device plugins are only ever loaded dynamically, none of *their* imports are visible to PyInstaller's static analysis either — this bit in practice: the first packaged build launched fine but threw `ModuleNotFoundError` (`yaml`, `rxn_bench_ui.connections.base`) the moment a device widget actually got constructed, since `connections/base.py` (used by every device's `generated_connection.py`) and `pyyaml` (used by some device `connection.py`/`workspace_loader.py` files) are only reachable through that dynamic path. The spec's `hiddenimports` now includes `collect_submodules("rxn_bench_ui")` (covers first-party gaps like `connections.base` without hand-listing every submodule; only walks the real installed `rxn_bench_ui` package tree, so it can't accidentally pull in `devices/*/frontend/`) plus an explicit `"yaml"` (the one third-party package device plugins depend on that core doesn't import directly). `packaging/entrypoint.py` also gained a `RXN_BENCH_UI_SELFTEST=1` mode (`make dist-check`) that actually constructs every discovered device widget inside the frozen build and exits nonzero on the first failure — a plain launch-and-see-if-it-crashes smoke test isn't enough to catch this class of bug, since nothing tries to load a device plugin until a widget for it is actually requested. A second entrypoint mode, `RXN_BENCH_UI_RUN_SCRIPT=<path>`, runs an experiment script via `runpy` inside the bundle instead of launching the GUI: the Experiment Runner (`core/experiment_panel.py`) can't launch `python script.py` in a frozen build (`sys.executable` is the GUI exe, not Python — doing so just opened a second UI), so when `sys.frozen` it re-execs the bundle with that env var set; the bundle ships `rxn_bench_client`+grpc, so bench-driving scripts run directly. Source/dev runs still launch the script with the real interpreter. PyInstaller does not cross-compile — a Windows `.exe` (the required target per `TODO-AI.md` §1.2) needs to be built on Windows (e.g. a `windows-latest` CI runner), not on this Linux dev setup; only a Linux onedir build has been produced and verified (via `make dist-check`) so far.

---

## 3. Connection Layer Pattern

The frontend connection layer is intentionally split into generated boilerplate and handwritten behavior.

| File | Purpose |
|---|---|
| `devices/<name>/frontend/connection_spec.yaml` | Human-authored manifest of streams, signals, decode types, and commands |
| `devices/<name>/frontend/generated_connection.py` | Generated Qt signals, stream startup, and typed command wrappers |
| `devices/<name>/frontend/connection.py` | Human-maintained subclass with decode handlers, convenience methods, and workflows |
| `rxnbench/frontend/src/rxn_bench_ui/connections/base.py` | Shared gRPC channel lifecycle, reconnect handling, stream cancellation, `_spawn_stream()`, `_call()`, and `_fire()` |

### Generator boundary

Only generate connection boilerplate.

Do **not** generate:

- widgets
- workflows
- app/core behavior
- dataclasses
- handwritten convenience methods

This keeps regeneration useful without letting generated code sprawl into the human UI layer.

---

## 4. Backend Layout

`rxnbench/backend/pyproject.toml` is still the uv workspace root and still owns the shared dev venv, `Makefile`, `install.sh`, and `scripts/install_service.sh` — but its `[tool.uv.workspace] members` now point out to `../../devices/<name>/backend` instead of holding the packages directly. `client/` is not a device and stays inside `rxnbench/backend/`.

### Gantry package

```text
devices/gantry/backend/src/rxn_bench_gantry/
├── server.py
├── _cli.py
├── feature.py
├── interfaces.py
├── controller.py
├── motion_engine.py
├── homing_manager.py
├── toolhead_manager.py
├── workspace_manager.py
├── moonraker_client.py
├── mock_moonraker.py
├── moonraker_discovery.py
├── machine_config.py
├── workspace_config.py
├── plate_geometry.py
├── toolhead_config.py
├── homing_state.py
├── session_log.py
├── errors.py
├── labware/
├── toolheads/
└── workspace/
```

Main responsibilities:

- Expose the Gantry SiLA feature.
- Keep controller logic hardware-agnostic through `MotionClientProtocol`.
- Route physical movement through `MotionEngine` and Moonraker.
- Persist homing and workspace state.
- Enforce safe-clearance movement and toolhead-aware bounds.
- Log session events to append-only JSONL files.

### pH package

```text
devices/ph_sensor/backend/src/rxn_bench_ph/
├── server.py
├── _cli.py
├── feature.py
├── interfaces.py
├── atlas_ph_sensor.py
├── ezo_commands.py                 ← transport-agnostic EZO command set (shared)
├── atlas_scientific_driver.py      ← EZO over I2C (commands + status-byte parsing)
├── atlas_scientific_uart_driver.py ← EZO over UART/serial
├── base_sensor.py
├── base_driver.py                  ← I2C transport base (AbstractI2CDriver)
├── i2c_bus.py                      ← SMBusI2C adapter
├── mock_i2c.py                     ← EZO I2C protocol emulator
├── mock_uart.py                    ← EZO UART protocol emulator
├── mock_ph_sensor.py
├── enums.py
└── session_log.py
```

Main responsibilities:

- Expose the pH SiLA feature.
- Keep pH feature logic decoupled from concrete sensor implementation through `PHSensorProtocol`.
- Speak the Atlas EZO-pH command protocol over **either I2C or UART**: `ezo_commands.EZOCommandSet`
  holds the transport-agnostic commands (`read_ph`, `calibrate_*`, `get_slope`, …) once, and the two
  drivers (`AtlasScientificEZO` for I2C, `AtlasScientificEZOUart` for UART) each supply only the
  byte-level send/receive. `server.py` selects the transport at startup via `RXN_BENCH_PH_TRANSPORT`
  (`i2c` default / `uart`), with `RXN_BENCH_PH_SERIAL_PORT`/`RXN_BENCH_PH_BAUD` for the serial path.
- Support mock pH readings for development (`MockPHSensor`), plus `MockI2CBus` **and** `MockEZOUart`,
  protocol emulators that exercise the *real* driver stack end-to-end without hardware on each transport.
- Bridge smbus2 to the driver's raw write/read interface via `i2c_bus.SMBusI2C`
  (EZO circuits speak raw I2C byte streams, not the SMBus register protocol); the UART driver talks to
  a pyserial `Serial` (or any `write`/`read_until` object) directly.
- Keep pH-specific calibration concepts inside the pH package.

### Camera package

```text
devices/camera/backend/src/rxn_bench_camera/
├── server.py
├── _cli.py
├── feature.py
├── interfaces.py
├── crowsnest_camera.py
├── camera_config.py
├── mock_camera.py
├── session_log.py
└── image_log.py
```

Main responsibilities:

- Expose the Camera SiLA feature (`LatestImage` observable property, `SetCaptureInterval` command).
- Keep feature logic decoupled from concrete camera implementation through `CameraProtocol` (one method: `capture() -> bytes`).
- Bridge to Crowsnest's underlying streamer (ustreamer by default) over plain HTTP via `crowsnest_camera.CrowsnestCamera` - Crowsnest itself has no API, it only supervises the real streamer process.
- Support a mock camera for development (`MockCamera`, returns a dependency-free placeholder PPM image - no imaging library needed).
- Archive every capture to `logs/images/` (`image_log.ImageLog`, pruned after 7 days - shorter than the 30-day JSONL default since binary frames are heavier) alongside the usual JSONL event log.
- SiLA's `Binary` basic type (`bytes` Python annotation) is used for the image property; `gen_proto.py`/`gen_connections.py` gained generic support for it (a `message Binary { bytes value = 1; }` wrapper, matching the CDK's own inline-payload wire encoding for payloads under its 2**21-byte binary-transfer threshold) - the first non-Real/Boolean/SString primitive type used by any device.

### Client package

```text
rxnbench/backend/client/src/rxn_bench_client/
├── client.py
├── instruments.py
└── data_logger.py
```

Main responsibilities:

- Provide script-level connection/session management.
- Attach instruments dynamically with `bench.connect(name, cls, server=...)`.
- Support experiment logging and pause/stop checks.

---

## 5. Current Capabilities

| Area | Status |
|---|---|
| Backend package split | Done |
| Per-device SiLA server processes | Done |
| Gantry motion feature | Done |
| Workspace/well movement layer | Done |
| Toolhead YAML configs | Done |
| Labware YAML configs | Done |
| Mock Moonraker | Done |
| pH SiLA feature | Done |
| Mock pH sensor | Done |
| PySide6 frontend shell | Done |
| Frontend device plugin architecture | Done |
| Gantry frontend widget | Done |
| pH frontend widget | Done |
| Generic FDL-driven device inspector (`GenericDeviceWidget`) | Done, including dynamic FDL→protobuf construction, structured/list params, observable commands, typed input widgets |
| Frontend pH connection | Done — uses generated protobuf stubs (`proto/ph_sensor_pb2.py`); the hand-rolled varint helpers are gone (from pH *and* the device template) |
| Shared frontend connection base | Done |
| Per-device generated connection layer | Done |
| Session JSONL logs | Done |
| CSV viewer and experiment notes panels | Done |
| Multi-tab frontend workspaces | Done |
| `SiLAService.GetImplementedFeatures` discovery | Done |
| Proto drift check for all devices | Done — `make check-proto` covers gantry, pH, camera, and the template; protos come from per-device manifests in `rxnbench/backend/scripts/gen_proto.py` (the old gantry-only script is gone) |
| Backend experiment-lock gating of motion RPCs | Done — `AcquireExperimentLock` returns a secret token; motion/toolhead/workspace commands accept a `Token` parameter and reject non-holders with `ExperimentLockError` while the lock is held; homing commands are always rejected while locked; Pause/Resume/Stop stay tokenless so the UI can always halt a run. `ForceReleaseExperimentLock` (tokenless, logged, confirm-guarded button on the UI banner) recovers a lock stranded by a killed script; the Experiment Runner's Stop sends SIGINT before SIGTERM so scripts normally release cleanly. Verified end-to-end against a live mock server. |
| Labware geometry served from backend (`GetLabware`) | Done — single source of truth for plate dimensions; the deck canvases and `rxn_bench_client.get_workspace_wells()` fetch it instead of hardcoding grids (the frontend's 24-well A1 offsets had already drifted ~9 mm from the backend's) |
| Workspace-aware dynamic safe clearance-travel height | Done (first slice of TODO-AI.md §1.1's Z-referencing rework) — `PlateGeometry.plate_height_mm` (deck to plate top surface) feeds `WorkspaceManager.max_labware_top_z()`, which `GantryController._safe_clearance_z` folds in alongside the bare-carriage floor and active tip hang-down, plus a configurable `MachineConfig.z_clearance_padding_mm` (default 5mm) margin. Replaces a flat 50mm constant that had no awareness of what labware was actually on the deck. See the gap below re: placeholder `plate_height_mm` values. |
| Per-well engagement-depth safety check | Done (second slice of TODO-AI.md §1.1) — `move_to_well` now docks at the target well's actual opening (`WorkspaceManager.resolve_well()`'s Z is now `origin_z + plate_height_mm`, not the raw plate mount height) instead of the workspace's generic clearance height, and rejects the move up front (`MotionLimitError`) if the active toolhead's `z_engage` exceeds that specific well's `well_depth_mm` via the new `WorkspaceManager.get_well_depth()`. Fixes a real bug the clearance-height change above exposed: a fixed relative `z_engage` descent from a now-variable clearance height no longer reliably reached into a shorter plate's wells when a taller container shared the same deck. The engagement-depth check is skipped when `override_unvalidated=True` (same flag as the unvalidated-geometry gate) — the toolhead calibration wizard (`toolhead_calibration_dialog.py`) always passes it and never calls `engage_tool`, so a toolhead's *configured* `z_engage` exceeding a shallower calibration plate's depth isn't a real collision risk there, only for the normal `move_to_well`-then-`engage_tool` flow (which doesn't pass it on real hardware). |
| Non-contact Z-reference calibration (hover + optional paper shim) | Done (third slice of TODO-AI.md §1.1 — the Z-reference/calibration UX rework) — both the homing dialog's Z Reference step and the toolhead calibration wizard's Z-touch step now offer hovering the tip at a known height instead of touching a surface directly. Homing: if a workspace with a `calibration_reference_well` is loaded, jogging to hover at that plate's known top surface (`resolve_reference_plate_height()`, new in `workspace_loader.py`) and confirming calls the newly-frontend-exposed `set_z(height)` (existed backend-side already; only the connection-layer wiring was missing) instead of always declaring 0 - falls back to the original touch-the-deck behavior when no workspace is loaded, since there's nothing else to hover over. Toolhead calibration: an optional "hover over reference plate" checkbox (only enabled when a reference plate is resolved) computes `tip_offset_z` from the known plate height instead of requiring a direct touch; the original touch method is kept as the always-available default, not replaced. Both dialogs also support an optional "paper shim" checkbox (default ~0.1mm, a rough estimate) so contact is felt by hand via a shim rather than the motor driving the tip into a hard surface - noted as likely impractical in wet-lab conditions, so eyeball-only stays the simple fallback. Verified end-to-end against a mock server (real `SetZ`/`CalibrateToolheadTipZ` RPCs, not just UI rendering). Gap: the *whole* homing state (X/Y limits and Z reference together) is still skippable only as one bundle via the existing "already homed?" page - Z isn't yet independently invalidatable the way X/Y limits are, so redoing X/Y after a bump also means redoing Z even if it was still good. |
| X/Z and Y/Z workspace side views | Done (fourth slice of TODO-AI.md §1.1 — phase 3, the Z-reference/calibration UX rework, is deferred) — `devices/gantry/frontend/workspace_loader.py` gained `DeckSideViewCanvas` (X/Z or Y/Z elevation) and `DeckViewPanel` (a Top/Side-X/Side-Y selector over `WorkspaceCanvas` + two `DeckSideViewCanvas` instances, all three kept live regardless of which is visible). Both the Live and Configuration tabs now hold a `DeckViewPanel` instead of a bare `WorkspaceCanvas`. Side views draw each plate's height + well-bottom line, the deck floor (Z=0), the server's real safe clearance-travel height, and - for the active well, if a toolhead is active - a precise engagement-depth marker. Backend: `GantryController.get_safe_clearance_z()` (new) and `GetLimits`'s pipe-delimited string gained a 7th `safe_clearance_z` field (no proto change - it was already a single SString blob) so the frontend never keeps an independently-computed copy of the safety formula. `GantryConnection` re-fetches it after a workspace op and on toolhead switches (not just at connect), since both change the value. Verified by launching the real widget against an isolated mock server and screenshotting all 3 views in both tabs. |
| Workspace YAML source of truth | Done — `GetWorkspaceYaml`/`Subscribe_CurrentWorkspaceYaml` read from the controller's workspace manager, so name-loaded (`SetWorkspace`) and boot-restored workspaces are visible to clients (previously only `LoadWorkspaceYaml` updated a feature-level cache) |
| Multi-toolhead support (two heads mounted at once) | Done — mount confirmations are **per-head** and survive activation switches: confirm each physically installed head once at setup, then scripts alternate between them unattended (`set_toolhead` is a pure software switch; `mount_toolhead` is idempotent). `move_to_well` refuses a head that was never confirmed mounted (`ToolheadNotMountedError`) or whose geometry is unvalidated. Homing invalidation moved from switching to the *physical-change* events (confirm/clear mounted, remove head), and only when state actually changes — so a mid-script switch no longer kills `save_and_park`. `ToolheadInfo` streams `mounted_toolheads` (pipe-delimited) so both UI slots show their own head's mount readiness; each slot's Activate switches the active head, the matching slot shows the ACTIVE badge, and mount/remove/calibrate only enable on the active slot. Verified end-to-end against a live mock server. |
| Mock I2C bus (`MockI2CBus`) + SMBus adapter (`SMBusI2C`) | Done — the real pH driver stack runs end-to-end against the EZO emulator in tests; `SMBusI2C` fixes a latent crash where `smbus2.SMBus` was passed directly to a driver expecting raw `write`/`read` |
| pH EZO-pH over UART/serial (alongside I2C) | Done and **verified on real hardware** (2026-07-13) — `AtlasScientificEZOUart` speaks the EZO serial protocol (`cmd\r`, CR-terminated `*OK`/`*ER`-framed replies, continuous mode disabled at startup) sharing the command set with the I2C driver via `ezo_commands.EZOCommandSet`; selected by `RXN_BENCH_PH_TRANSPORT=uart` (+ `RXN_BENCH_PH_SERIAL_PORT`/`RXN_BENCH_PH_BAUD`). `MockEZOUart` runs the real UART driver stack in tests. This is now the reference bench's live transport (EZO on the Pi's GPIO 14/15 → `/dev/ttyAMA0` @ 9600, set via a `rxn-bench-ph.service` systemd drop-in); pyserial (in the `[rpi]` extra) was installed into the deployed pH venv. Follow-up: fold pyserial into a rebuilt offline bundle so a from-scratch reinstall includes it (it was hand-installed on the live Pi). |
| Frontend test suite | Done (first pass) — `rxnbench/frontend/tests/`: generator golden checks per device, `_format_error` decoding, labware→canvas spec conversion; run with `make test` (headless) |
| Client test suite | Done — `rxnbench/backend/client/tests/` (37 tests, `make test-client`, in CI): `RxnBenchClient` session wiring (connect/close, lock-holder selection, release-failure safety), `at_well` sequencing incl. disengage-on-exception, pause/stop polling, CSV logging, lock-token attachment to every gantry command, server-labware well enumeration, and the PHProbe convenience readers — all against fakes, no servers needed |
| CI workflow | Done — `.github/workflows/ci.yml` runs both backend suites, frontend tests, `check-proto`, and `check-connections` on push/PR |
| Moonraker HTTP timeouts | Done — all requests carry (connect, read) timeouts, so a wedged Moonraker can no longer hang the server while holding the hardware lock |
| Split-service install/systemd scripts | Done |
| One-command offline Pi installer | Done (TODO-AI.md §1.2) — `rxnbench/backend/scripts/build_offline_bundle.sh` (dev machine, has internet) resolves every device's dependencies via `uv export`, downloads aarch64 wheels from PyPI/piwheels/the private UniteLabs index, vendors a matching `uv` binary, and tarballs repo source + wheelhouse. `scripts/install_offline.sh` (the Pi, no internet needed) installs `uv`, installs the selected devices fully offline, runs each device's optional `install/setup_drivers.sh` hook (pH sensor's enables I2C headlessly), opens firewall ports if `ufw` is active, and installs/starts systemd units. `install_service.sh`'s per-device case statement became a data-driven registry (`_DEVICE_REGISTRY`) with an `--offline <wheelhouse>` flag, so both scripts share one place that knows how to install a device — adding device #3 to this flow is one registry line, not new script logic. See [docs/deployment.md](../deployment.md). Fixed a real port/UUID collision found along the way: `camera` and `device_template` both hardcoded port 50053 and shared a UUID (device_template moved to 50099). |
| Device-first repo layout (`devices/<name>/{backend,frontend}`) | Done |
| `device_template` frontend half (was backend-only) | Done |
| `motion_platform.proto` matches backend dataclasses/feature | Done |
| pH backend real test suite (driver, sensor, feature layers) | Done |
| Gantry backend real test suite (motion engine sequencing, homing state machine, toolhead-aware bounds, controller, feature, well/workspace math, mock Moonraker) | Done |
| Experiment-lock frontend visibility | Done — banner + Pause/Resume/Stop wired to `experiment_active_changed` in the main widget (`_set_controls_locked` disables toolhead-management buttons, including the ones that launch the Homing/Toolhead Calibration dialogs). Homing and Toolhead Calibration dialogs also disable their own jog/confirm controls if the lock is acquired while already open. Backend-level RPC gating now backs this up (see the lock-token row above), so the UI disabling is defense-in-depth, not the only barrier. |
| `generated_connection.py` drift check | Done — `make check-connections` (new `rxnbench/frontend/Makefile`) regenerates every device's `generated_connection.py` from its `connection_spec.yaml` and diffs; `make gen-connections` regenerates in place. Loops over `devices/*/frontend/connection_spec.yaml` generically, so it covers new devices automatically. |
| `motion_platform` proto stubs live under `devices/gantry/frontend/proto/` | Done, moved out of the shared `proto/` tree, which now only holds `sila_service_pb2` (framework-level, genuinely shared). `gen_proto.py`, the `rxnbench/backend/Makefile` proto targets, and `connection_spec.yaml`'s `proto_module` all point at the new location; `make check-proto` still passes |
| Frozen-build-aware frontend plugin discovery + PyInstaller onedir packaging (Linux) | Done (groundwork for TODO-AI.md §1.2) — `rxn_bench_ui/devices/__init__.py` now resolves `devices/` from `sys.executable`'s directory when `sys.frozen` is set, instead of always walking up from `__file__`; dev-mode behavior is unchanged. `rxnbench/frontend/packaging/` (spec, entrypoint, `copy_device_plugins.py`) plus `make dist` produce a onedir build and stage `devices/*/frontend/` next to the executable. First pass looked fine (launched headlessly, discovery found the right modules) but only actually loading a device widget in the frozen build surfaced two `ModuleNotFoundError`s (`yaml`, `rxn_bench_ui.connections.base`) invisible to both PyInstaller's static analysis and that first verification pass — fixed via `collect_submodules("rxn_bench_ui")` + explicit `yaml` in the spec's `hiddenimports`. `make dist-check` (new) now actually constructs every discovered device widget inside the real frozen build and confirms no ImportError — all 4 pass. See "Standalone executable packaging" above. |
| `new-device` dev-agent skill (TODO-AI.md §2.2) | Done — `.claude/skills/new-device/SKILL.md`, alongside the existing `debug`/`feature`/`review-design` skills. Before scaffolding anything, it requires reading every existing device's backend `Protocol`/feature and frontend widget/connection layer to check whether the new hardware fits an existing interface (e.g. a second pH-style probe should reuse `rxn_bench_ph`, not get its own package); only a genuine misfit walks the `device_template` copy/rename checklist. Explicitly caps generated complexity at `device_template`'s Protocol+mock+feature shape and treats falling back to `GenericDeviceWidget` (no custom frontend widget) as a valid outcome, not a shortcut to avoid. |
| Camera device (TODO-AI.md §2.1) | Done — `rxn_bench_camera` SiLA server (port 50053) streams a `LatestImage` observable property (SiLA `Binary`/`bytes`) captured from a Crowsnest-managed webcam stream via a plain-HTTP `CrowsnestCamera` driver, with a runtime-adjustable `SetCaptureInterval` command, mock camera path (dependency-free placeholder PPM image), and per-capture archiving to `logs/images/` alongside the usual JSONL event log. `CameraProtocol` is a single `capture() -> bytes` method, so Crowsnest is one implementation, not the whole abstraction, per the TODO's acceptance criteria. Frontend plugin (`devices/camera/frontend/`) shows the live image plus an interval control. `rxn_bench_client.Camera` adds `snapshot()`/`save_snapshot()`/`set_capture_interval()`. Required extending the shared `gen_proto.py`/`gen_connections.py` generators with a `Binary` primitive wrapper (`bytes` → SiLA's native `Binary` basic type) — the first non-Real/Boolean/SString primitive any device has needed; verified end-to-end against a live mock server (real gRPC subscribe + command call, not just unit tests). See the gap below re: unverified real Crowsnest wiring. |

---

## 6. Current Gaps

These are the active issues worth tracking now.

| Gap | Location | Priority | Notes |
|---|---|---:|---|
| Verify real pH I2C path on the Pi | `rxn_bench_ph/i2c_bus.py` + physical bench | Low | Superseded: the reference bench runs the pH probe over **UART**, not I2C (the EZO is wired to the Pi's GPIO 14/15 TX/RX and left in its default UART mode). The **UART** path (`AtlasScientificEZOUart` on `/dev/ttyAMA0` @ 9600) is verified against the physical EZO circuit as of 2026-07-13 - live pH readings confirmed on the deployed `rxn-bench-ph` service. The I2C driver remains complete and mock-tested but is no longer on this bench's runtime path, so verifying it against real I2C hardware is now low priority. |
| Migrate configs to pydantic | gantry config models | Medium | Gives validation, clearer errors, and JSON Schema export. |
| Entry-points plugin refactor for frontend device discovery | `rxn_bench_ui/devices/__init__.py` | Medium | Current `all_devices()` loader uses `importlib.util.spec_from_file_location` to scan a `devices/` folder (repo-root in dev, next to the executable when frozen — see "Standalone executable packaging" above). An `importlib.metadata` entry-points refactor would still be a cleaner long-term model, symmetric with the backend's uv workspace members, but isn't required for the packaging work — file-location scanning works fine pointed at either directory. |
| Add TLS + authentication deployment guide | docs/config | Low until shared-network deployment | Bare, unauthenticated gRPC is acceptable for isolated bench development but not for a shared lab network. Note: Moonraker's own HTTP API on the Pi is itself unauthenticated by default, so network exposure bypasses *all* gantry safety logic (bounds, clearance, experiment lock) the moment this leaves an isolated bench network — TLS on the SiLA/gRPC layer alone would not close that hole. The experiment-lock token is a coordination mechanism, not authentication: any client on the network can still acquire the lock when it's free. |
| Verify sample-holder labware dimensions | `labware/6_well_sample_holder.yaml` (+ header comment in `3_well_sample_holder.yaml` still says "6-Well") | Medium | The 6-well file was scaffolded with standard 6-well *plate* dimensions as placeholders — caliper-verify spacing/offsets against the physical holder before running wells on it. The 15-well and 3-well holders already carry measured-looking values. |
| Verify `plate_height_mm` across all labware types | `labware/*.yaml` | Medium | New field (deck to plate top surface) added to every bundled labware file to drive dynamic safe clearance-travel height. All 6 are currently `well_depth_mm + ~3mm` estimates, not measured — caliper-verify before trusting them for collision safety, same as the existing well-geometry gap above. |
| Measure pH probe `tip_x` / `tip_y` | `toolheads/ph_probe/ph_probe_toolhead.yaml` | Low | Current values are still placeholders — the physical measurement itself hasn't happened. The guard is implemented: `ToolheadGeometry.geometry_validated` (default `True`, `False` for `ph_probe`) logs a warning on `set_toolhead()` and `GantryController.move_to_well()` refuses to run with a `UnvalidatedGeometryError` unless `override_unvalidated=True` is passed. Plain `move_to()`/`jog()` are unaffected — only well-targeted moves are gated. |
| Verify Crowsnest wiring on the real SV08 | `rxn_bench_camera/crowsnest_camera.py` + physical bench | High | The HTTP client, config loading, feature, and mock path are complete and tested, but `crowsnest_base_url`/`crowsnest_snapshot_path` defaults (ustreamer's `/snapshot`) have not been confirmed against a live Crowsnest deployment - verify on a bench session and adjust `~/.rxn_bench/machine.yaml` if the SV08's `crowsnest.conf` uses mjpg-streamer instead. |
| Tune camera image-log retention for the deployment's storage budget | `rxn_bench_camera/image_log.py`, `~/.rxn_bench/machine.yaml` | Medium | Default is `capture_interval_s=30`, 7-day retention on `logs/images/`; this can still add up to several GB on a Pi's SD card at higher capture rates. No pressure to change until a real bench session shows it's a problem. |
| Windows PyInstaller build (CI) | `rxnbench/frontend/packaging/` | High for TODO-AI.md §1.2 | PyInstaller doesn't cross-compile, so `make dist` has only been run and verified on Linux so far. The required target is a Windows `.exe` — needs a `windows-latest` GitHub Actions job (or a Windows VM) running the same `make dist` and producing a downloadable artifact. Also unverified on Windows: Qt platform plugin bundling (`windows` platform plugin vs. this session's `offscreen`/`xcb` testing) and whether `pyinstaller-hooks-contrib`'s grpc/zeroconf hooks need Windows-specific hidden imports. |
| Verify installer's auto-pin + multicast-route service on a from-scratch reinstall | `rxnbench/backend/scripts/install_offline.sh` (+ `install_service.sh`) | Medium | On the gatewayless bench network discovery silently fails despite healthy services, two independent causes (see the 2026-07-13 CHANGELOG entry): the CDK auto-detect advertises `127.0.0.1`, and multicast can't egress with no default route. Fixed: `install_offline.sh` auto-detects the host's primary IPv4 (`hostname -I`) and (a) pins `sila_server.hostname` via a `~/.rxn_bench/<device>.json` override (new `--advertise-ip <IP>` flag to `install_service.sh`; `--no-pin` opts out), and (b) when the multicast group isn't already routable, installs a boot-time `rxn-bench-mcast-route.service` oneshot (`ip route replace 224.0.0.0/4 dev <iface>`). Device systemd units now wait on `network-online.target` since they bind a specific IP. **Note:** `discovery.network_interfaces` is a no-op — the CDK connector (`unitelabs/cdk/connector.py`) never forwards the discovery config to its multicast socket, so `IP_MULTICAST_IF` is never set; the route is the only lever (confirmed empirically). The pin/route logic was validated in isolation and applied by hand to the live Pi (discovery confirmed working), but the full installer path hasn't been re-run end-to-end on a from-scratch reinstall yet. Repo config templates intentionally keep `hostname: "0.0.0.0"` — the correct *generic* default; the pin/route are deployment-time only. |

---

## 7. Immediate Next Work

1. Bench-verify the real pH I2C path on the Pi (code is done; the physical
   EZO circuit hasn't been exercised through `SMBusI2C` yet).

2. Measure the pH probe's `tip_x`/`tip_y` and flip `geometry_validated` to true.

3. Start pydantic migration for config models:
   - `ToolheadConfig`
   - `WorkspaceConfig`
   - `MachineConfig`
   - labware definitions

---

## 8. Stable Design Decisions

- Keep one backend package per physical/logical device.
- Keep one SiLA server process per device.
- Keep each device self-contained as one `devices/<name>/{backend,frontend}` folder at the repo root (a "drop in or remove" unit), while the SiLA/gRPC machine-separation boundary and the uv-workspace/single-frontend-app mechanics stay exactly as before — this is a file-layout change, not an architecture change. `rxnbench/backend/` and `rxnbench/frontend/` hold the non-device-specific app/workspace machinery only.
- Keep shared connection lifecycle code in `connections/base.py`.
- Keep generated connection code next to the device it belongs to.
- Keep widgets handwritten.
- Keep workflows handwritten.
- Keep device discovery server-sourced through `SiLAService.GetImplementedFeatures`.
- Keep toolhead and labware definitions YAML/config-driven.
- Keep experiment scripts using `rxn_bench_client` rather than directly depending on frontend code.
- Keep the shared uv workspace venv for local dev/test only. Production deployment gives gantry and ph_sensor their own standalone venv each (via `scripts/install_service.sh`), so either service can be updated/restarted without affecting the other.
- Duplicate small utilities per device rather than extracting a shared common package. `rxn_bench_gantry/session_log.py` and `rxn_bench_ph/session_log.py` are functionally identical (byte-for-byte except one docstring word) — this is intentional, not drift to fix. Keeping each device's backend self-contained (no shared runtime dependency between otherwise-independent device packages) outweighs de-duplicating ~70 lines. (Build scripts are the exception: `rxnbench/backend/scripts/gen_proto.py` is one generator with a per-device manifest, because generated wire formats must not drift between devices.)
- Both drift checks (`make check-proto`, `make check-connections`) and all test suites now run in CI (`.github/workflows/ci.yml`) on every push/PR, in addition to being runnable locally before a PR.
- Experiment lock uses a **token**, not caller identity: `AcquireExperimentLock` returns a secret; state-changing commands take an optional `Token` parameter checked backend-side. The UI never sends a token (so it is locked out during runs, except Pause/Resume/Stop); `rxn_bench_client.Gantry` attaches its token automatically. This is coordination between cooperating clients, not authentication (see the TLS gap in §6).
- Plate/labware geometry is served by the gantry backend (`GetLabware`, YAML) and consumed by the frontend canvases and the experiment client. Never hardcode plate dimensions outside `rxn_bench_gantry/labware/*.yaml` — the frontend's former hardcoded table had already drifted ~9 mm from the backend on the 24-well plate. `PlateGeometry.plate_height_mm` is now part of that same single source of truth and drives `GantryController`'s clearance-travel math — a labware YAML's dimensions are never duplicated into a second, separately maintained safety constant.
- Multiple toolheads can be physically mounted at once; exactly one is *active* (its geometry drives targeting/bounds). Mount confirmations are per-head and survive activation switches — switching (`set_toolhead`) is a pure software change that preserves homing state, so scripts alternate between pre-confirmed heads without operator interaction. Homing invalidates on *physical* changes only (confirming/clearing a mount, removing a head) and only when the state actually changes (re-confirming is a no-op). Well-targeted moves require the active head to be confirmed mounted and geometry-validated; plain `move_to`/`jog` are ungated. The two frontend slots are selection presets over this model.
- Frontend plugins talk to servers **only** through their device connection (`connection.py` / generated base). No raw `grpc.insecure_channel` or hand-rolled protobuf in widgets — the last two violations (workspace loader's ad-hoc channels; pH/template varint helpers) were removed in this pass.

---

## 9. Platform Roadmap

**Long-term goal:** grow Rxn Bench from a single bench (gantry + pH) into more of an all-around laboratory control platform — many/heterogeneous devices, not just this one bench. This doesn't change anything in sections 1-8; the device-first layout, one-SiLA-server-per-device model, and mock/real hardware split already scale toward this goal without rework.

Near-term, in priority order:

1. **Workflow runner in `rxn_bench_client` — not a YAML DSL, a thin structural layer over plain Python scripts.** Experiment scripts stay arbitrary Python (loops, conditionals, numpy/pandas, adaptive logic) — that expressiveness is worth keeping, not replacing. What's missing is a lightweight decorator/context-manager per step that gives a `WorkflowRunner` enough structure to: retry/resume from the failed step instead of rerunning the whole script, know which devices a step touches before running it (so a future scheduler can avoid device contention), and record a structured per-step audit trail alongside the existing JSONL session logs. Design constraint: each step must carry an idempotency/side-effect flag, and resume-from-failed-step must default to requiring human confirmation before re-running or skipping a step — physical actions (dispensed liquid, a probe already lowered into a well) can't be rolled back the way a database transaction can. Pure Python, no new service or database; lives inside the existing client package. (MADSci itself does the analogous thing — YAML workflows plus an escape-hatch `ExperimentApplication` Python class — because pure declarative workflows aren't enough either.)
2. ~~**Prove the pattern with a real third device.**~~ Done — the camera device (TODO-AI.md §2.1, see §5) added only `devices/camera/{backend,frontend}` plus one shared-generator extension (the `Binary` primitive wrapper in `gen_proto.py`/`gen_connections.py`, needed because images are the first non-Real/Boolean/SString payload any device has sent — a generic addition, not a camera-specific carve-out). Nothing in `core/` or `device_registry.py` changed. The bar from this item is cleared; machine-vision work (error detection, run monitoring, workspace inspection, calibration assistance) can build on `CameraProtocol`'s raw `capture() -> bytes` without further abstraction changes.

Done, as of 2026-07-01: all four gaps in the generic FDL-driven device widget (dynamic protobuf message construction, structured/list parameter support, observable-command support, typed input widgets with validation).

Deferred until a concrete trigger (not speculative work):

| Capability | Build when... |
|---|---|
| Resource/labware/inventory tracking | Juggling enough reagents/labware that a human can't track it by eye |
| Multi-bench discovery + TLS | A second physical bench/room actually exists (today's mDNS discovery is local-subnet only) |
| Autonomous experiment loop | Unattended overnight runs are actually wanted, not just multi-instrument human-supervised control |

---

## 10. Deferred Ideas

The following ideas are intentionally deferred, out of the active architecture plan:

- AI-assisted device onboarding
- runtime `OnboardingFeature`
- hot-reloadable generated device manifests
- fully metadata-driven workflow generation

These are interesting, but they should not block the current bench from becoming stable, installable, and testable.
