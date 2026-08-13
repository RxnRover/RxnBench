# Rxn Bench - Current State

**Last cleaned:** July 2, 2026  
**Purpose:** Keep the active architecture, current gaps, and next engineering moves visible without preserving every historical migration note.

---

## 1. Architecture Snapshot

Rxn Bench is a modular lab automation stack built around separate SiLA device servers and a PySide6 operator UI.

```text
Operator Machine
└── rxn_bench_ui  ── gRPC/SiLA ── Device Host (Raspberry Pi in the reference deployment)
    ├── core shell              ├── rxn-bench-gantry      :50051 ── Moonraker/Klipper motion platform
    ├── device plugins          ├── rxn-bench-ph          :50052 ── pH sensor stack
    └── experiment scripts      ├── rxn-bench-camera      :50053 ── Crowsnest webcam stream
        └── rxn_bench_client    └── rxn-bench-dosing-pump :50054 ── Atlas EZO-PMP peristaltic pump
```

Each backend device is split into a **capability** package (the SiLA feature + Protocol interface, hardware-agnostic) and one or more **driver** packages (a concrete implementation of that Protocol, plus that hardware's CAD/toolhead config) - see "Capability + driver split" below and [Supported-Devices.md](../Supported-Devices.md) for the full capability<->driver registry:

| Capability package | Role | Reference driver package |
|---|---|---|
| `rxn_bench_gantry` | Gantry SiLA server | `rxn_bench_moonraker_driver` (Moonraker/Klipper) |
| `rxn_bench_ph` | pH SiLA server | `rxn_bench_atlas_ezo_ph_driver` (Atlas Scientific EZO-pH, I2C or UART) |
| `rxn_bench_camera` | Camera SiLA server | `rxn_bench_crowsnest_camera_driver` (Crowsnest webcam stream) |
| `rxn_bench_dosing_pump` | Dosing pump SiLA server | `rxn_bench_atlas_ezo_pmp_driver` (Atlas Scientific EZO-PMP) |
| `rxn_bench_client` | Experiment script client | Script-friendly session manager and instrument wrappers (no driver split - not device-specific) |
| `rxn_bench_template` | Device template | Reference capability package for adding future devices (no real driver - see below) |

The frontend is a PySide6 app with a stable split between core shell code and per-device plugins.

Per-package class/package UML diagrams (generated via `make uml`, see each package's `docs/Makefile`) are checked in at [docs/architecture/uml/](../docs/architecture/uml/).

### Device-first layout

Each device is a self-contained top-level folder, not split across the `rxnbench/backend` and `rxnbench/frontend` trees. Each `devices/<name>/{capability,driver}` folder is now also its own git repo, wired into this checkout as a **git submodule** (`.gitmodules`) - one step towards the JOSS-publication goal of the Automated_Chem_Bench repo becoming a master/meta repo over `rxnbench`, `rxn_bench_client`, and per-device/per-driver repos. `.gitmodules` currently points at local paths (`../rxn-bench-device-repos/rxn-bench-<name>-<side>`) pending those repos being pushed to GitHub - a fresh clone needs `git submodule update --init` (or `git clone --recurse-submodules`) before anything under `devices/` is populated:

```text
devices/
├── gantry/
│   ├── capability/    <- rxn_bench_gantry (backend/) + rxn_bench_gantry_frontend (frontend/) (submodule)
│   └── driver/        <- rxn_bench_moonraker_driver + hardware_models/ (SV08 mounting hardware) (submodule)
├── ph_sensor/
│   ├── capability/    <- rxn_bench_ph (backend/) + rxn_bench_ph_sensor_frontend (frontend/) (submodule)
│   └── driver/        <- rxn_bench_atlas_ezo_ph_driver + hardware_models/ + toolhead/ (ph_probe_toolhead.yaml) (submodule)
├── camera/
│   ├── capability/    <- rxn_bench_camera (backend/) + rxn_bench_camera_frontend (frontend/) (submodule)
│   └── driver/        <- rxn_bench_crowsnest_camera_driver (submodule)
├── dosing_pump/
│   ├── capability/    <- rxn_bench_dosing_pump (backend/) + rxn_bench_dosing_pump_frontend (frontend/) (submodule)
│   └── driver/        <- rxn_bench_atlas_ezo_pmp_driver (submodule)
└── device_template/
    └── capability/    <- reference capability package for new devices (backend/ + frontend/) (submodule; no driver/ - see below)
```

This is a file-layout convention only - it does **not** relax the hard machine-separation rule below. `devices/<name>/capability/backend/` and `devices/<name>/driver/backend/` still only ship to the device host (a Raspberry Pi in the reference deployment); `devices/<name>/capability/frontend/` still only runs on the operator machine as part of the single `rxn_bench_ui` app; nothing under `frontend/` imports anything under `backend/`. `rxnbench/backend/` (uv workspace root, `client/`, `install.sh`) and `rxnbench/frontend/` (the app itself: `core/`, `connections/`, `proto/`) hold the code that isn't specific to one device. Submodule status is orthogonal to the uv workspace/editable-path wiring: `rxnbench/backend/pyproject.toml`'s `[tool.uv.workspace] members` and `rxnbench/frontend/pyproject.toml`'s `[tool.uv.sources]` editable paths reference these folders by the same relative path regardless of whether git tracks them as plain directories or submodules, so splitting into submodules required zero changes there.

### Capability + driver split

Every device backend already separated a **capability** (a `Protocol` + SiLA feature implementation, hardware-agnostic) from a **driver** (the concrete class implementing that Protocol) at the file level - `PHSensorProtocol` vs. `AtlasScientificEZOUart`, `CameraProtocol` vs. `CrowsnestCamera`, `DosingPumpProtocol` vs. `AtlasDosingPump`, `MotionClientProtocol` vs. `MoonrakerClient`. The capability/driver package split just promotes that existing boundary to a package (and repo) boundary:

- **Capability package** (`rxn_bench_<name>`, keeps its existing name): SiLA feature, Protocol interface(s), generic mock (one that satisfies the Protocol directly with no vendor wire-protocol emulation - `MockPHSensor`, `MockCamera`, `MockMoonrakerClient`), session/image logging, `_cli.py`, `server.py`. Depends on `unitelabs-cdk` and its default driver package, nothing hardware-specific.
- **Driver package** (`rxn_bench_<vendor>_driver`, new): the concrete vendor driver, its wire-protocol emulator mocks (`MockI2CBus`, `MockEZOUart` - these emulate the *vendor's byte-level protocol*, unlike the capability's generic mock, so they live here), that hardware's CAD (`hardware_models/`), and its toolhead config if it mounts on the gantry (`toolhead/<name>_toolhead.yaml`). Registers under a `rxn_bench.<name>_drivers` entry-point group (e.g. `rxn_bench.ph_drivers`) so the capability's `server.py` has **zero import-time dependency on any concrete driver** - a second vendor's driver for the same capability (e.g. a different pH probe brand) registers under the same group with no capability-side changes, exactly like frontend plugin discovery (§2).

`server.py`'s driver selection: `RXN_BENCH_<NAME>_DRIVER` (default: the reference driver's registered name, e.g. `atlas_ezo` for pH) picks which entry point to load via `importlib.metadata.entry_points(group=...)`; `RXN_BENCH_MOCK=1` still short-circuits to the capability's own generic mock **except** for the dosing pump, where the existing mock (`MockDosingPump`) is itself built on the real Atlas driver stack over a protocol emulator (`class MockDosingPump(AtlasDosingPump)` - preserves realistic command encoding/timing) and so lives in the driver package too, loaded via a second registered entry point (`atlas_ezo_pmp_mock`) rather than a capability-side import.

**Uv workspace note:** only capability packages are `[tool.uv.workspace] members`; driver packages are reached via a plain `{path = ..., editable = true}` dependency of their capability (same pattern as `rxn-bench-client`), **not** `{workspace = true}`. Declaring both capability and driver as explicit workspace members with reciprocal `{workspace = true}` sources breaks package-metadata builds from a clean venv/lockfile on uv 0.11.21 ("references a workspace... but is not a workspace member", even though it is) - a real uv limitation hit while doing this split, not a design choice. Driver tests run via plain `uv run pytest <path>` (no `--package`, since they're not workspace members) but are still installed into the shared workspace venv transitively.

**Toolhead config aggregation:** a toolhead config (e.g. the pH probe's mount geometry/engage-depth YAML) is data the *driver* owns - gantry doesn't know what a pH probe is, it just mounts whatever config it's handed - but `rxn_bench_gantry.toolhead_config.ToolheadConfig.load()` reads from one bundled directory (`rxn_bench_gantry/toolheads/<name>/<name>_toolhead.yaml`). `rxnbench/backend/scripts/aggregate_toolheads.py` bridges this at install time: it copies every `devices/*/driver/toolhead/*_toolhead.yaml` into gantry's bundled `toolheads/` directory before gantry's venv is built (wired into `make install` and `install_offline.sh`, ahead of `install_service.sh`). The aggregated per-toolhead folders are gitignored build output, not checked in - re-run `make install` (or `python3 rxnbench/backend/scripts/aggregate_toolheads.py` directly) after a fresh checkout/submodule init or gantry's `test_toolhead_manager.py` tests fail with the toolhead missing.

`device_template` has no driver package: its mock is a generic Protocol stub (`MockMyDevice`, not vendor-specific), so there's nothing to split out. A real new device following this template adds a `driver/` package alongside its own hardware, using the pH sensor split as the worked example (it exercises every piece: two transports, wire-protocol mocks, hardware CAD, and a toolhead config).

---

## 2. Frontend Layout

```text
rxnbench/frontend/src/rxn_bench_ui/
├── app.py
├── discovery.py
├── themes.py
├── proto/
│   └── sila_service_pb2.py   <- shared SiLA framework stub only; device protos live with their device
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
    └── __init__.py   <- merges entry-point discovery with a repo-root devices/*/frontend/ scan (see below)
```

Each device's actual plugin code lives outside this tree, in its own repo (submodule at the same path), as a pip-installable package under `devices/<name>/frontend/src/rxn_bench_<name>_frontend/` - the same `src/` layout backend device packages already used:

```text
devices/gantry/capability/frontend/
├── pyproject.toml           <- declares the "gantry" entry in the rxn_bench.devices group
└── src/rxn_bench_gantry_frontend/
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

devices/ph_sensor/capability/frontend/
├── pyproject.toml
└── src/rxn_bench_ph_sensor_frontend/
    ├── __init__.py
    ├── connection_spec.yaml
    ├── generated_connection.py
    ├── connection.py
    ├── widget.py
    ├── proto/
    │   ├── ph_sensor.proto
    │   └── ph_sensor_pb2.py
    └── ui/

devices/camera/capability/frontend/
├── pyproject.toml
└── src/rxn_bench_camera_frontend/
    ├── __init__.py
    ├── connection_spec.yaml
    ├── generated_connection.py
    ├── connection.py
    ├── widget.py
    └── proto/
        ├── camera.proto
        └── camera_pb2.py

devices/dosing_pump/capability/frontend/
├── pyproject.toml
└── src/rxn_bench_dosing_pump_frontend/
    ├── __init__.py
    ├── connection_spec.yaml
    ├── generated_connection.py
    ├── connection.py
    ├── widget.py
    ├── proto/
    │   ├── dosing_pump.proto
    │   └── dosing_pump_pb2.py
    └── ui/
        └── dosing_pump_widget.ui
```

`devices/device_template/capability/frontend/` mirrors the same shape (`src/rxn_bench_device_template_frontend/`), including its own
`proto/my_device{.proto,_pb2.py}` stubs, so the template teaches the compiled-stub
pattern end-to-end (the hand-rolled varint helpers it used to demonstrate are gone).

### Frontend rule

Each device plugin owns its own widget and connection layer. Core only handles application shell behavior, discovery, device selection, workspace tabs, theme propagation, and generic fallback UI.

### Device plugin contract

Each device's `rxn_bench_<name>_frontend/__init__.py` exports:

```python
FEATURE_FRAGMENTS: list[str]
def create_widget(server, theme: dict) -> QWidget: ...
```

`rxn_bench_ui/devices/__init__.py`'s `all_devices()` merges two discovery paths:

1. **Entry points** (primary, for the five first-party devices) - each device frontend package declares a `"rxn_bench.devices"` entry point in its own `pyproject.toml` (e.g. `gantry = "rxn_bench_gantry_frontend"`); `all_devices()` loads every entry in that group via `importlib.metadata.entry_points(group="rxn_bench.devices")`. Each package is a real pip-installable dependency of `rxn-bench-ui` (`rxnbench/frontend/pyproject.toml`'s `[tool.uv.sources]`, editable path to `devices/<name>/frontend`), so `uv sync` in `rxnbench/frontend/` installs all five automatically. Imports into `rxn_bench_ui` are absolute now (`from rxn_bench_ui.discovery import DiscoveredServer`, `import rxn_bench_gantry_frontend.proto.motion_platform_pb2 as _pb`) rather than the old `rxn_bench_ui.devices.<name>`-relative form, since these packages no longer live inside that namespace.
2. **Directory scan** (fallback, zero-rebuild drop-in) - anything with a flat `devices/<name>/frontend/__init__.py` (repo-root in a source checkout, next to the executable when frozen) is still loaded via `importlib.util.spec_from_file_location`, exactly as before. This is for a device that isn't packaged as a formal dependency yet (e.g. an experimental/community device dropped into a deployed install without a rebuild).

The two don't collide: a migrated device's code lives under `src/rxn_bench_<name>_frontend/` now, so it has no flat `__init__.py` for the scan to find - entry points and directory scan are mutually exclusive per device by construction, not by an explicit dedup check. `core/device_registry.py` just calls `all_devices()`; adding a new frontend device (via either path) should not require editing the core registry.

### Standalone executable packaging

`rxnbench/frontend/packaging/` holds a PyInstaller setup (`rxn-bench-ui.spec`, `entrypoint.py`) that produces a onedir build of the app. The five first-party device packages are baked into the bundle at build time now (see below), not staged as a folder - `make dist` runs PyInstaller, then `packaging/copy_device_plugins.py` (now only relevant to the directory-scan fallback: it stages any `devices/<name>/frontend/` with a flat `__init__.py` into a `devices/` folder next to the executable; the five first-party devices have none, so it stages nothing for them today), then `packaging/copy_workflows.py`, which stages `rxnbench/backend/client/scripts/` into a `Scripts/` folder and `devices/gantry/capability/backend/src/rxn_bench_gantry/workspace/definitions/*.yaml` into a `Workspaces/` folder next to it - so an install ships ready-to-run example experiment scripts and importable workspace templates, not just the app itself. `Workspaces/` is explicitly examples to import-and-edit, not live device config: the gantry backend has its own copy of `workspace/definitions/` on the bench Pi that it actually loads named workspaces from. The Experiment Runner's "Browse" dialog (`core/experiment_panel.py`) and the gantry plugin's "Import Workspace YAML" dialog (`rxn_bench_gantry_frontend/workspace_loader.py`) both default to these staged folders when frozen (and to the equivalent source-tree paths in a dev checkout), via `_default_scripts_dir()`/`_default_workspaces_dir()`. The CI Windows build (`.github/workflows/windows-installer.yml`) runs the same three staging steps directly rather than via `make dist`, so both call sites need updating together. `installer.iss` needs no changes for this - its `[Files]` section already copies everything under the build dir recursively. `.ui` files and `assets/` under `rxn_bench_ui/core/` are bundled explicitly as PyInstaller `datas` (not picked up by static analysis since they're loaded at runtime via `QUiLoader`/`Path(__file__).parent`).

Because both the directory-scanned fallback plugins and the five entry-point packages are only ever reached dynamically at runtime (`importlib.util.spec_from_file_location` for the former, `importlib.metadata.entry_points()` for the latter), none of their imports are visible to PyInstaller's static analysis - this bit in practice twice. First: the original directory-scan path threw `ModuleNotFoundError` (`yaml`, `rxn_bench_ui.connections.base`) the moment a device widget actually got constructed, since `connections/base.py` and `pyyaml` are only reachable through that dynamic path - fixed via `collect_submodules("rxn_bench_ui")` (covers first-party gaps without hand-listing every submodule; only walks the real installed `rxn_bench_ui` package tree) plus an explicit `"yaml"` in `hiddenimports`. Second, migrating to entry points introduced a *different* invisible-import problem: `collect_all()` per device package (`rxn_bench_gantry_frontend`, etc.) bundles their code, but `entry_points()` itself works by scanning `*.dist-info` metadata on `sys.path` - metadata `collect_all()` does **not** bundle. Without `copy_metadata("rxn-bench-gantry-frontend")` (and one per device) added explicitly, a frozen build would launch fine but silently discover zero devices (no error - `entry_points(group=...)` just returns empty). Verified against a real onedir Linux build via `make dist-check`: all 5 device widgets construct successfully inside the frozen exe.

`packaging/entrypoint.py` also gained a `RXN_BENCH_UI_SELFTEST=1` mode (`make dist-check`) that actually constructs every discovered device widget inside the frozen build and exits nonzero on the first failure - a plain launch-and-see-if-it-crashes smoke test isn't enough to catch this class of bug, since nothing tries to load a device plugin until a widget for it is actually requested. A second entrypoint mode, `RXN_BENCH_UI_RUN_SCRIPT=<path>`, runs an experiment script via `runpy` inside the bundle instead of launching the GUI: the Experiment Runner (`core/experiment_panel.py`) can't launch `python script.py` in a frozen build (`sys.executable` is the GUI exe, not Python - doing so just opened a second UI), so when `sys.frozen` it re-execs the bundle with that env var set; the bundle ships `rxn_bench_client`+grpc, so bench-driving scripts run directly. This bit the same way device plugins did: `rxn_bench_client` and its `sila2`/`grpc_tools` dependencies are only ever imported by user scripts loaded dynamically via `runpy`, so PyInstaller's static analysis never saw them and the first script run threw `ModuleNotFoundError: No module named 'rxn_bench_client'` - the spec now `collect_all`s all three (grpc/zeroconf/yaml are already pulled in by the UI). `grpc_tools` in particular needs collecting even once `sila2` is bundled: sila2 compiles FDL into gRPC stubs at runtime via `grpc_tools.protoc`, whose compiled `_protoc_compiler` extension does `from grpc_tools import grpc_version` internally (invisible to static analysis) and needs the `_proto/*.proto` well-known types as data files. Verified by running a script through the real frozen exe (it reaches live-server discovery, not an ImportError). Source/dev runs still launch the script with the real interpreter. PyInstaller does not cross-compile - a Windows `.exe` (the required target per `TODO-AI.md` §1.2) needs to be built on Windows (e.g. a `windows-latest` CI runner), not on this Linux dev setup; only a Linux onedir build has been produced and verified (via `make dist-check`) so far.

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

`rxnbench/backend/pyproject.toml` is still the uv workspace root and still owns the shared dev venv, `Makefile`, `install.sh`, and `scripts/install_service.sh` - but its `[tool.uv.workspace] members` now point out to `../../devices/<name>/capability/backend` (plus each real device's `../../devices/<name>/driver/backend`, reached from the capability's own editable path dependency rather than being a workspace member itself - see "Capability + driver split" in §1) instead of holding the packages directly. `client/` is not a device and stays inside `rxnbench/backend/`.

Deliberately no `[project]` table on this root: `uv sync` at a pure-workspace root (no `[project]`) installs every member by default, which `install.sh`/`Makefile`'s `install` target rely on; adding `[project]` narrows bare `uv sync` to just the root's own deps, silently uninstalling every workspace member. Its `pytest`/`pyyaml` deps (needed by `scripts/gen_capability.py` and `tests/test_gen_capability.py`) live in a `[dependency-groups] dev` block instead, which `uv` supports without a `[project]` table and which `uv sync` still installs by default.

### Capability Spec Pattern

Mirrors §3's frontend split, one layer further back: each device's `interfaces.py` (a `typing.Protocol`) is generated from a declarative spec instead of hand-maintained in lockstep with `feature.py`.

| File | Purpose |
|---|---|
| `devices/<name>/capability/backend/src/rxn_bench_<name>/<FeatureClass>.capability.yaml` | Human-authored spec: properties/commands per Protocol, optional/opt-in protocols, feature-only members with no Protocol backing, excluded (permanently hand-written) protocols |
| `devices/<name>/capability/backend/src/rxn_bench_<name>/interfaces.py` | Generated Protocol signatures - do not hand-edit. Gantry is a partial exception: only the `GantryControllerProtocol` block between `# --- BEGIN/END GENERATED ---` markers is owned by the generator; `MotionClientProtocol` above the markers stays hand-written (it's a low-level driver-transport interface `controller.py` consumes, not part of the SiLA-facing capability) |
| `devices/<name>/capability/backend/src/rxn_bench_<name>/<FeatureClass>.capability.md` | Generated human-readable snapshot (feature identity, each Protocol's members, feature-only members, excluded protocols) - documentation only, not consumed at runtime; the running SiLA server already produces an equivalent FDL live via `unitelabs-cdk`'s decorators on `feature.py` |
| `rxnbench/backend/scripts/gen_capability.py` | The generator - `make gen-capability` regenerates every device, `make check-capability` is the CI drift check |
| `rxnbench/backend/tests/test_gen_capability.py` | Golden-file tests (generated output == checked-in files) plus a static `ast`-based cross-check that `feature.py`'s declared SiLA members correspond to the spec - catches the class of bug a golden-file diff alone can't (e.g. `feature.py` calling a hardware method the Protocol never declared) |

`feature.py` stays 100% hand-written, always - only `interfaces.py` (pure signatures in every device already, confirmed empty-body Protocol methods across all five packages) is generated. Migrating all 5 devices caught two real pre-existing bugs the AST cross-check surfaced: camera's `set_capture_interval` had no `CameraProtocol` backing (pure feature-local state, now declared `feature_only`), and gantry's `feature.py` called `calibrate_toolhead_tip`/`calibrate_toolhead_tip_z` on the controller despite neither ever being declared in `GantryControllerProtocol` (added to the spec, closing the gap).

### Gantry package

```text
devices/gantry/capability/backend/src/rxn_bench_gantry/
├── server.py
├── _cli.py
├── feature.py
├── interfaces.py
├── controller.py
├── motion_engine.py
├── homing_manager.py
├── toolhead_manager.py
├── workspace_manager.py
├── mock_moonraker.py        <- generic MotionClientProtocol simulator, no Moonraker wire emulation - stays capability-side
├── machine_config.py
├── workspace_config.py
├── plate_geometry.py
├── toolhead_config.py
├── homing_state.py
├── session_log.py
├── errors.py
├── labware/
├── toolheads/               <- aggregation target for every device driver's toolhead config, see §1
└── workspace/

devices/gantry/driver/backend/src/rxn_bench_moonraker_driver/
├── moonraker_client.py
└── moonraker_discovery.py
devices/gantry/driver/hardware_models/   <- SV08 mounting brackets, belt clamps, etc.
```

Main responsibilities:

- Expose the Gantry SiLA feature.
- Keep controller logic hardware-agnostic through `MotionClientProtocol`.
- Route physical movement through `MotionEngine` and the registered `rxn_bench.gantry_drivers` driver (`moonraker` by default).
- Persist homing and workspace state.
- Enforce safe-clearance movement and toolhead-aware bounds.
- Log session events to append-only JSONL files.

### pH package

```text
devices/ph_sensor/capability/backend/src/rxn_bench_ph/
├── server.py
├── _cli.py
├── feature.py
├── interfaces.py
├── base_sensor.py
├── mock_ph_sensor.py
├── enums.py
└── session_log.py

devices/ph_sensor/driver/backend/src/rxn_bench_atlas_ezo_ph_driver/
├── atlas_ph_sensor.py
├── ezo_commands.py                 <- transport-agnostic EZO command set (shared)
├── atlas_scientific_driver.py      <- EZO over I2C (commands + status-byte parsing)
├── atlas_scientific_uart_driver.py <- EZO over UART/serial
├── base_driver.py                  <- I2C transport base (AbstractI2CDriver)
├── i2c_bus.py                      <- SMBusI2C adapter
├── mock_i2c.py                     <- EZO I2C protocol emulator
└── mock_uart.py                    <- EZO UART protocol emulator
devices/ph_sensor/driver/hardware_models/   <- pH probe toolhead housing CAD
devices/ph_sensor/driver/toolhead/ph_probe_toolhead.yaml
```

Main responsibilities:

- Expose the pH SiLA feature.
- Keep pH feature logic decoupled from concrete sensor implementation through `PHSensorProtocol`.
- Speak the Atlas EZO-pH command protocol over **either I2C or UART**: `ezo_commands.EZOCommandSet`
  holds the transport-agnostic commands (`read_ph`, `calibrate_*`, `get_slope`, …) once, and the two
  drivers (`AtlasScientificEZO` for I2C, `AtlasScientificEZOUart` for UART) each supply only the
  byte-level send/receive. The driver package's `build_sensor()` (registered as `atlas_ezo` under
  `rxn_bench.ph_drivers`) selects the transport at startup via `RXN_BENCH_PH_TRANSPORT`
  (`i2c` default / `uart`), with `RXN_BENCH_PH_SERIAL_PORT`/`RXN_BENCH_PH_BAUD` for the serial path.
- Support mock pH readings for development (`MockPHSensor`, capability-side), plus `MockI2CBus`
  **and** `MockEZOUart` (driver-side), protocol emulators that exercise the *real* driver stack
  end-to-end without hardware on each transport.
- Bridge smbus2 to the driver's raw write/read interface via `i2c_bus.SMBusI2C`
  (EZO circuits speak raw I2C byte streams, not the SMBus register protocol); the UART driver talks to
  a pyserial `Serial` (or any `write`/`read_until` object) directly.
- Keep pH-specific calibration concepts inside the pH package.

### Camera package

```text
devices/camera/capability/backend/src/rxn_bench_camera/
├── server.py
├── _cli.py
├── feature.py
├── interfaces.py
├── camera_config.py
├── mock_camera.py
├── session_log.py
└── image_log.py

devices/camera/driver/backend/src/rxn_bench_crowsnest_camera_driver/
└── crowsnest_camera.py
```

Main responsibilities:

- Expose the Camera SiLA feature (`LatestImage` observable property, `SetCaptureInterval` command).
- Keep feature logic decoupled from concrete camera implementation through `CameraProtocol` (one method: `capture() -> bytes`).
- Bridge to Crowsnest's underlying streamer (ustreamer by default) over plain HTTP via `crowsnest_camera.CrowsnestCamera` (registered as `crowsnest` under `rxn_bench.camera_drivers`) - Crowsnest itself has no API, it only supervises the real streamer process.
- Support a mock camera for development (`MockCamera`, returns a dependency-free placeholder PPM image - no imaging library needed).
- Archive every capture to `logs/images/` (`image_log.ImageLog`, pruned after 7 days - shorter than the 30-day JSONL default since binary frames are heavier) alongside the usual JSONL event log.
- SiLA's `Binary` basic type (`bytes` Python annotation) is used for the image property; `gen_proto.py`/`gen_connections.py` gained generic support for it (a `message Binary { bytes value = 1; }` wrapper, matching the CDK's own inline-payload wire encoding for payloads under its 2**21-byte binary-transfer threshold) - the first non-Real/Boolean/SString primitive type used by any device.

### Dosing pump package

```text
devices/dosing_pump/capability/backend/src/rxn_bench_dosing_pump/
├── server.py
├── _cli.py
├── feature.py
├── interfaces.py
└── session_log.py

devices/dosing_pump/driver/backend/src/rxn_bench_atlas_ezo_pmp_driver/
├── atlas_dosing_pump.py             <- DosingPumpProtocol impl over a command driver
├── ezo_pmp_commands.py              <- transport-agnostic EZO-PMP command set
├── atlas_scientific_uart_driver.py  <- EZO-PMP over UART/serial
├── mock_uart.py                     <- EZO-PMP protocol emulator (simulates dispensing)
└── mock_device.py                   <- MockDosingPump: real driver stack over the emulator (registered
                                        as atlas_ezo_pmp_mock, NOT a generic capability-side mock - see §1)
```

Main responsibilities:

- Expose the DosingPump SiLA feature (`VolumeDispensed`/`Dispensing` observable properties;
  `Dispense`, `DoseOverTime`, `SetFlowRate`, `DispenseContinuously`, `Stop`, `SetPaused`,
  `SetInverted`, calibration and total-volume commands).
- Keep feature logic decoupled from the concrete pump through `DosingPumpProtocol`.
- Speak the Atlas EZO-PMP command protocol over UART, split the same way as the pH package:
  `ezo_pmp_commands.EZOPumpCommandSet` holds the transport-agnostic commands and
  `AtlasScientificEZOPumpUart` supplies the byte-level send/receive. This is a *deliberate
  duplicate* of the pH package's shape, not shared code - see the per-device duplication
  decision in §8. Only UART is implemented (the reference bench is UART-only); the command
  set stays transport-agnostic so an I2C driver could be added without rework.
- Handle two EZO-PMP protocol quirks the pH circuit doesn't have: `*DONE` is both the reply to
  `X` (stop) *and* an unsolicited interrupt when a dispense finishes on its own (the driver only
  accepts it as a reply when the in-flight command expects one, so a dose completing mid-query
  can't corrupt an unrelated reading), and `*MINVOL`/`*TOOFAST` are command rejections distinct
  from plain `*ER`.
- Turn the pump's two *toggle* commands (`P` pause, `Invert`) into idempotent setters by reading
  current state first, so scripts assert a desired state instead of tracking parity.
- Keep the device interface **minimal, with opt-in capability protocols for the rest**.
  `DosingPumpProtocol` is 12 methods every dosing pump has; `SupportsCalibration`,
  `SupportsDirectionInvert`, and `SupportsDiagnostics` are separate `runtime_checkable`
  protocols the feature probes with `isinstance`, rejecting just those commands (naming what
  is missing) on hardware that lacks them. This is what makes the frontend reusable: plugins
  are matched to a **SiLA feature identifier**, not a model, so any server advertising
  `DosingPump` gets the same widget/connection/proto/client with no new frontend code - a
  second pump model is one driver class plus one line in `server.py`'s `_DRIVERS` registry
  (selected by `RXN_BENCH_PUMP_DRIVER`). Correspondingly, **no model-specific numbers live in
  the widget**: the Rate ceiling comes from the server's `MaxFlowRate` at runtime and per-pump
  minimums are enforced by the device and surfaced as errors, rather than hardcoding one
  pump's limits into shared UI.
- Keep circuit housekeeping (`find`, LED, `sleep`/`wake`, protocol lock) driver-level only, *not*
  on the SiLA feature - same split as `rxn_bench_ph`. `sleep()` requires a paired `wake()`: the
  byte that wakes a sleeping EZO is consumed doing so and is not executed (the circuit answers
  `*WA`), so the command is silently lost; `wake()` absorbs that throwaway exchange. `sleep()`
  powers down the control system only, not the 12-24V motor supply. `Baud`/`Factory`/`Name`/
  I2C-switch, `O` (output-parameter selection, which would change the string `R` parsing depends
  on), and `Dstart` (dispense-at-startup) are intentionally unimplemented.
- Support a mock pump (`MockDosingPump`) built on `MockEZOPumpUart`, a protocol emulator that
  runs the *real* driver stack without hardware and simulates dispensing against an injectable
  clock, so a dose really does progress and complete over its requested duration.

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
| Generic FDL-driven device inspector (`GenericDeviceWidget`) | Done, including dynamic FDL->protobuf construction, structured/list params, observable commands, typed input widgets |
| Frontend pH connection | Done - uses generated protobuf stubs (`proto/ph_sensor_pb2.py`); the hand-rolled varint helpers are gone (from pH *and* the device template) |
| Shared frontend connection base | Done |
| Per-device generated connection layer | Done |
| Session JSONL logs | Done |
| CSV viewer and experiment notes panels | Done |
| Multi-tab frontend workspaces | Done |
| `SiLAService.GetImplementedFeatures` discovery | Done |
| Proto drift check for all devices | Done - `make check-proto` covers gantry, pH, camera, and the template; protos come from per-device manifests in `rxnbench/backend/scripts/gen_proto.py` (the old gantry-only script is gone) |
| Backend experiment-lock gating of motion RPCs | Done - `AcquireExperimentLock` returns a secret token; motion/toolhead/workspace commands accept a `Token` parameter and reject non-holders with `ExperimentLockError` while the lock is held; homing commands are always rejected while locked; Pause/Resume/Stop stay tokenless so the UI can always halt a run. `ForceReleaseExperimentLock` (tokenless, logged, confirm-guarded button on the UI banner) recovers a lock stranded by a killed script; the Experiment Runner's Stop sends SIGINT before SIGTERM so scripts normally release cleanly. `RxnBenchClient.close()` also unconditionally parks a connected gantry (`save_and_park()`) before releasing the lock - on normal completion, a UI stop (`ExperimentStopped`), or any unhandled exception - so a killed/failed run never leaves the gantry's saved homing state stale enough to need a manual re-home; scripts no longer need their own explicit `save_and_park()` call. Verified end-to-end against a live mock server. |
| Labware geometry served from backend (`GetLabware`) | Done - single source of truth for plate dimensions; the deck canvases and `rxn_bench_client.get_workspace_wells()` fetch it instead of hardcoding grids (the frontend's 24-well A1 offsets had already drifted ~9 mm from the backend's) |
| Workspace-aware dynamic safe clearance-travel height | Done (first slice of TODO-AI.md §1.1's Z-referencing rework) - `PlateGeometry.plate_height_mm` (deck to plate top surface) feeds `WorkspaceManager.max_labware_top_z()`, which `GantryController._safe_clearance_z` folds in alongside the bare-carriage floor and active tip hang-down, plus a configurable `MachineConfig.z_clearance_padding_mm` (default 5mm) margin. Replaces a flat 50mm constant that had no awareness of what labware was actually on the deck. See the gap below re: placeholder `plate_height_mm` values. |
| Intra-plate travel optimization | Done - `move_to_well` between wells of the *same* plate travels at just that plate's own top + padding (`GantryController._plate_clearance_z`) instead of the full-deck max, cutting raise/lower time on multi-well scans. "Same plate" is decided statelessly from the current tip position vs. the target plate's footprint (`WorkspaceManager.plate_footprint_bounds`); plain `move_to` and cross-plate hops keep the full clearance. Does NOT yet account for the X-gantry crossbar sweeping a taller same-Y-row plate (see gap). |
| Well-depth-aware engagement depth (blended, not toolhead-only) | Done (second slice of TODO-AI.md §1.1) - `move_to_well` docks at the target well's actual opening (`WorkspaceManager.resolve_well()`'s Z is `origin_z + plate_height_mm`, not the raw plate mount height) instead of the workspace's generic clearance height, so the engagement descent is a physically meaningful drop into the well regardless of how tall the clearance height needed to be for other labware. The descent itself is no longer the toolhead's raw configured `z_engage` (one hand-tuned number): `GantryController._effective_engage_depth` blends it with the docked well's own measured `well_depth_mm` (mean of the two) and caps the result at `well_depth_mm - MachineConfig.engage_bottom_margin_mm` (default 2mm) so the tip always stops a fixed gap above the bottom. This *replaced* the earlier hard rejection of `z_engage > well_depth`: a toolhead configured deeper than a shallower plate's wells (e.g. the bench `ph_probe`'s `z_engage=40` in a 36mm-deep 96-well plate) now runs, capped, instead of refusing the move. The controller tracks the docked well (`_current_well_label`, set by `move_to_well`, cleared by any plain `move_to`/`jog`); with no docked well or no active toolhead there is nothing to blend against and `engage_tool(depth=…)` keeps its literal meaning. `disengage_tool` applies the same blend so an engage/disengage pair is symmetric (returns the tip to the opening). The frontend side-view engagement marker (`workspace_loader.effective_engage_depth`) mirrors the blend so the viz shows the real depth, minus the small backend-only bottom margin. `WorkspaceManager.get_well_depth()` remains the per-well depth source. |
| Non-contact Z-reference calibration (hover + optional paper shim) | Done (third slice of TODO-AI.md §1.1 - the Z-reference/calibration UX rework) - both the homing dialog's Z Reference step and the toolhead calibration wizard's Z-touch step now offer hovering the tip at a known height instead of touching a surface directly. Homing: if a workspace with a `calibration_reference_well` is loaded, jogging to hover at that plate's known top surface (`resolve_reference_plate_height()`, new in `workspace_loader.py`) and confirming calls the newly-frontend-exposed `set_z(height)` (existed backend-side already; only the connection-layer wiring was missing) instead of always declaring 0 - falls back to the original touch-the-deck behavior when no workspace is loaded, since there's nothing else to hover over. Toolhead calibration: an optional "hover over reference plate" checkbox (only enabled when a reference plate is resolved) computes `tip_offset_z` from the known plate height instead of requiring a direct touch; the original touch method is kept as the always-available default, not replaced. Both dialogs also support an optional "paper shim" checkbox (default ~0.1mm, a rough estimate) so contact is felt by hand via a shim rather than the motor driving the tip into a hard surface - noted as likely impractical in wet-lab conditions, so eyeball-only stays the simple fallback. Verified end-to-end against a mock server (real `SetZ`/`CalibrateToolheadTipZ` RPCs, not just UI rendering). Gap: the *whole* homing state (X/Y limits and Z reference together) is still skippable only as one bundle via the existing "already homed?" page - Z isn't yet independently invalidatable the way X/Y limits are, so redoing X/Y after a bump also means redoing Z even if it was still good. |
| X/Z and Y/Z workspace side views | Done (fourth slice of TODO-AI.md §1.1 - phase 3, the Z-reference/calibration UX rework, is deferred) - `devices/gantry/capability/frontend/workspace_loader.py` gained `DeckSideViewCanvas` (X/Z or Y/Z elevation) and `DeckViewPanel` (a Top/Side-X/Side-Y selector over `WorkspaceCanvas` + two `DeckSideViewCanvas` instances, all three kept live regardless of which is visible). Both the Live and Configuration tabs now hold a `DeckViewPanel` instead of a bare `WorkspaceCanvas`. Side views draw each plate's height + well-bottom line, the deck floor (Z=0), the server's real safe clearance-travel height, and - for the active well, if a toolhead is active - a precise engagement-depth marker. Backend: `GantryController.get_safe_clearance_z()` (new) and `GetLimits`'s pipe-delimited string gained a 7th `safe_clearance_z` field (no proto change - it was already a single SString blob) so the frontend never keeps an independently-computed copy of the safety formula. `GantryConnection` re-fetches it after a workspace op and on toolhead switches (not just at connect), since both change the value. Verified by launching the real widget against an isolated mock server and screenshotting all 3 views in both tabs. |
| Workspace YAML source of truth | Done - `GetWorkspaceYaml`/`Subscribe_CurrentWorkspaceYaml` read from the controller's workspace manager, so name-loaded (`SetWorkspace`) and boot-restored workspaces are visible to clients (previously only `LoadWorkspaceYaml` updated a feature-level cache) |
| Multi-toolhead support (two heads mounted at once) | Done - mount confirmations are **per-head** and survive activation switches: confirm each physically installed head once at setup, then scripts alternate between them unattended (`set_toolhead` is a pure software switch; `mount_toolhead` is idempotent). `move_to_well` refuses a head that was never confirmed mounted (`ToolheadNotMountedError`) or whose geometry is unvalidated. Homing invalidation moved from switching to the *physical-change* events (confirm/clear mounted, remove head), and only when state actually changes - so a mid-script switch no longer kills `save_and_park`. `ToolheadInfo` streams `mounted_toolheads` (pipe-delimited) so both UI slots show their own head's mount readiness; each slot's Activate switches the active head, the matching slot shows the ACTIVE badge, and mount/remove/calibrate only enable on the active slot. Verified end-to-end against a live mock server. |
| Mock I2C bus (`MockI2CBus`) + SMBus adapter (`SMBusI2C`) | Done - the real pH driver stack runs end-to-end against the EZO emulator in tests; `SMBusI2C` fixes a latent crash where `smbus2.SMBus` was passed directly to a driver expecting raw `write`/`read` |
| pH EZO-pH over UART/serial (alongside I2C) | Done and **verified on real hardware** (2026-07-13) - `AtlasScientificEZOUart` speaks the EZO serial protocol (`cmd\r`, CR-terminated `*OK`/`*ER`-framed replies, continuous mode disabled at startup) sharing the command set with the I2C driver via `ezo_commands.EZOCommandSet`; selected by `RXN_BENCH_PH_TRANSPORT=uart` (+ `RXN_BENCH_PH_SERIAL_PORT`/`RXN_BENCH_PH_BAUD`). `MockEZOUart` runs the real UART driver stack in tests. This is now the reference bench's live transport (EZO on the Pi's GPIO 14/15 -> `/dev/ttyAMA0` @ 9600, set via a `rxn-bench-ph.service` systemd drop-in); pyserial (in the `[rpi]` extra) was installed into the deployed pH venv. Follow-up: fold pyserial into a rebuilt offline bundle so a from-scratch reinstall includes it (it was hand-installed on the live Pi). |
| Frontend test suite | Done (first pass) - `rxnbench/frontend/tests/`: generator golden checks per device, `_format_error` decoding, labware->canvas spec conversion; run with `make test` (headless) |
| Client test suite | Done - `rxnbench/backend/client/tests/` (84 tests, `make test-client`, in CI): `RxnBenchClient` session wiring (connect/close, lock-holder selection, release-failure safety), `bench.devices` auto-discovery, `at_well` sequencing incl. disengage-on-exception, pause/stop polling, CSV logging, lock-token attachment to every gantry command, server-labware well enumeration, and the PHProbe convenience readers - all against fakes, no servers needed |
| `bench.devices.<name>` auto-discovery in `rxn_bench_client` | Done - kills the `bench.connect(name, Class, server=...)` boilerplate for the four built-in instruments. New `rxn_bench_client/devices.py`: `DEVICE_REGISTRY` maps a name to `(wrapper class, required SiLA feature)`; `discover_sila_clients()` scans the network once via `sila2.discovery.browser.SilaDiscoveryBrowser` (already probes every discovered server's advertised features - no hand-rolled mDNS/gRPC needed, unlike the frontend's `discovery.py`, which the client can't import anyway - separate machine boundary) and is cached on the client so later `bench.devices.<other>` accesses are instant; `DeviceNamespace.__getattr__` matches by `hasattr(client, feature)`, reuses an already-attached instrument (whether attached via a prior `bench.devices.<name>` access or an explicit `bench.connect(...)`) instead of reconnecting, and raises a clear error on zero or multiple matches. `client.py`'s `connect()` had its post-connection logic extracted into a shared `_attach()` so both paths behave identically (instrument tracking, lock acquisition) and always end up on `bench.<name>` too - `bench.devices.gantry is bench.gantry` holds. `bench.devices.raw(feature_name)` returns the unwrapped SiLA feature proxy for anything not in the small built-in registry, so nothing is ever forced to conform to one of the four wrapper classes. Fully additive - `bench.connect(...)` is unchanged and both styles mix freely in the same script. Verified against a live mock bench (`make start-mock`): real mDNS discovery + feature matching, explicit `connect()` and `bench.devices` interoperating on the same session. |
| CI workflow | Done - `.github/workflows/ci.yml` runs both backend suites, frontend tests, `check-proto`, and `check-connections` on push/PR |
| Moonraker HTTP timeouts | Done - all requests carry (connect, read) timeouts, so a wedged Moonraker can no longer hang the server while holding the hardware lock |
| Split-service install/systemd scripts | Done |
| One-command offline Pi installer | Done (TODO-AI.md §1.2) - `rxnbench/backend/scripts/build_offline_bundle.sh` (dev machine, has internet) resolves every device's dependencies via `uv export`, downloads aarch64 wheels from PyPI/piwheels/the private UniteLabs index, vendors a matching `uv` binary, and tarballs repo source + wheelhouse. `scripts/install_offline.sh` (the Pi, no internet needed) installs `uv`, installs the selected devices fully offline, runs each device's optional `install/setup_drivers.sh` hook (pH sensor's enables I2C headlessly), opens firewall ports if `ufw` is active, and installs/starts systemd units. `install_service.sh`'s per-device case statement became a data-driven registry (`_DEVICE_REGISTRY`) with an `--offline <wheelhouse>` flag, so both scripts share one place that knows how to install a device - adding device #3 to this flow is one registry line, not new script logic. See [docs/deployment.md](../docs/deployment.md). Fixed a real port/UUID collision found along the way: `camera` and `device_template` both hardcoded port 50053 and shared a UUID (device_template moved to 50099). |
| Device-first repo layout (`devices/<name>/{backend,frontend}`) | Done |
| `device_template` frontend half (was backend-only) | Done |
| `motion_platform.proto` matches backend dataclasses/feature | Done |
| pH backend real test suite (driver, sensor, feature layers) | Done |
| Gantry backend real test suite (motion engine sequencing, homing state machine, toolhead-aware bounds, controller, feature, well/workspace math, mock Moonraker) | Done |
| Experiment-lock frontend visibility | Done - banner + Pause/Resume/Stop wired to `experiment_active_changed` in the main widget (`_set_controls_locked` disables toolhead-management buttons, including the ones that launch the Homing/Toolhead Calibration dialogs). Homing and Toolhead Calibration dialogs also disable their own jog/confirm controls if the lock is acquired while already open. Backend-level RPC gating now backs this up (see the lock-token row above), so the UI disabling is defense-in-depth, not the only barrier. |
| `generated_connection.py` drift check | Done - `make check-connections` (`rxnbench/frontend/Makefile`) regenerates every device's `generated_connection.py` from its `connection_spec.yaml` and diffs; `make gen-connections` regenerates in place. Loops over `devices/*/frontend/src/*/connection_spec.yaml` generically, so it covers new devices automatically. |
| `motion_platform` proto stubs live under `devices/gantry/capability/frontend/src/rxn_bench_gantry_frontend/proto/` | Done, moved out of the shared `proto/` tree, which now only holds `sila_service_pb2` (framework-level, genuinely shared). `gen_proto.py`, the `rxnbench/backend/Makefile` proto targets, and `connection_spec.yaml`'s `proto_module` all point at the current location; `make check-proto` still passes |
| Device frontends split into standalone entry-points packages | Done - see "Device plugin contract"/"Standalone executable packaging" (§2). Two coupling points existed identically across all five devices and were fixed the same way in each: the relative `from ...discovery import DiscoveredServer` import (now absolute `rxn_bench_ui.discovery`) and `generated_connection.py`'s absolute `rxn_bench_ui.devices.<name>.proto.X_pb2` import (now `rxn_bench_<name>_frontend.proto.X_pb2`, driven by each `connection_spec.yaml`'s `proto_module` field so the generator reproduces it correctly instead of reverting it). `rxn_bench_ui/devices/__init__.py`'s `all_devices()` merges entry-point discovery with the pre-existing directory scan (kept as the zero-rebuild drop-in path). Verified: all 5 widgets construct headless via entry points, inside a real PyInstaller-frozen build (`make dist-check`), and via the full backend + frontend test suites. |
| Backend capability/driver split (all 4 real devices + repo topology for device_template) | Done - see "Capability + driver split" (§1) and the per-device package trees in §4. Every device's existing Protocol/driver file-level boundary was promoted to a package boundary: `rxn_bench_<name>` (capability, hardware-agnostic) + `rxn_bench_<vendor>_driver` (concrete implementation, hardware CAD, toolhead config), the latter registered under a `rxn_bench.<name>_drivers` entry-point group so `server.py` never imports a concrete driver directly. `rxnbench/backend/scripts/aggregate_toolheads.py` (new, wired into `make install`/`install_offline.sh`) copies each driver's toolhead config into gantry's bundled `toolheads/` directory at install time. Hit and worked around a real uv 0.11.21 limitation: two workspace members with reciprocal `{workspace = true}` sources fail package-metadata builds from a clean venv - drivers are plain editable-path dependencies of their capability instead, not workspace members. |
| All 19 device folders (10 frontend/backend-era + 9 capability/driver-era) split into their own git repos as submodules | Done - groundwork for the JOSS-publication repo restructure (master repo + per-package repos); see "Device-first layout" (§1). `.gitmodules` currently points at local repo paths under `../rxn-bench-device-repos/` pending GitHub hosting - CI's `submodules: true` checkout won't succeed until those are repointed. Verified end-to-end after every restructuring pass: full backend test suite (`make test` - capability + driver tests for all 4 devices), `check-proto`, full frontend suite, `check-connections`, and a real PyInstaller-frozen build (`make dist-check`) constructing all 5 device widgets via entry points. |
| Frozen-build-aware frontend plugin discovery + PyInstaller onedir packaging (Linux) | Done (groundwork for TODO-AI.md §1.2) - `rxn_bench_ui/devices/__init__.py` now resolves `devices/` from `sys.executable`'s directory when `sys.frozen` is set, instead of always walking up from `__file__`; dev-mode behavior is unchanged. `rxnbench/frontend/packaging/` (spec, entrypoint, `copy_device_plugins.py`) plus `make dist` produce a onedir build and stage `devices/*/frontend/` next to the executable. First pass looked fine (launched headlessly, discovery found the right modules) but only actually loading a device widget in the frozen build surfaced two `ModuleNotFoundError`s (`yaml`, `rxn_bench_ui.connections.base`) invisible to both PyInstaller's static analysis and that first verification pass - fixed via `collect_submodules("rxn_bench_ui")` + explicit `yaml` in the spec's `hiddenimports`. `make dist-check` (new) now actually constructs every discovered device widget inside the real frozen build and confirms no ImportError - all 4 pass. See "Standalone executable packaging" above. |
| `new-device` dev-agent skill (TODO-AI.md §2.2) | Done - `.claude/skills/new-device/SKILL.md`, alongside the existing `debug`/`feature`/`review-design` skills. Before scaffolding anything, it requires reading every existing device's backend `Protocol`/feature and frontend widget/connection layer to check whether the new hardware fits an existing interface (e.g. a second pH-style probe should reuse `rxn_bench_ph`, not get its own package); only a genuine misfit walks the `device_template` copy/rename checklist. Explicitly caps generated complexity at `device_template`'s Protocol+mock+feature shape and treats falling back to `GenericDeviceWidget` (no custom frontend widget) as a valid outcome, not a shortcut to avoid. |
| Dosing pump device (Atlas EZO-PMP) | Done - `rxn_bench_dosing_pump` SiLA server (port 50054) exposing all four datasheet dispensing modes (fixed volume, dose over time, constant flow rate, continuous) plus pause/stop/invert, single-point calibration, and net/absolute total-volume counters. `DosingPumpProtocol` is a new interface: the pump is an *actuator*, with no overlap with `PHSensorProtocol` (read/calibrate/slope), `CameraProtocol` (`capture()`), or the gantry's motion protocol - so it got its own device rather than reusing one. The Atlas EZO UART wire protocol *is* shared with `rxn_bench_ph`, but is deliberately duplicated per the per-device self-containment rule in §8. Frontend plugin (`devices/dosing_pump/capability/frontend/`) has a hand-built widget with dispense/dose/flow-rate controls, live volume, and totals; `rxn_bench_client.DosingPump` adds `dispense_and_wait()` alongside the raw commands. Required extending `gen_proto.py` with an `Integer` primitive wrapper (SiLA `Integer` = int64) for `GetCalibrationStatus` - the second generic generator addition after the camera's `Binary`, and verified to decode correctly against a live server. Verified end-to-end against a real mock server: progressive dispensing over gRPC, `Stop`'s float return, unobservable-property reads, error propagation for `*MINVOL`/`*TOOFAST`, and the real Qt widget constructed and driven headlessly. See the gap below re: unverified real hardware and the serial-port conflict with the pH probe. |
| Camera device (TODO-AI.md §2.1) | Done - `rxn_bench_camera` SiLA server (port 50053) streams a `LatestImage` observable property (SiLA `Binary`/`bytes`) captured from a Crowsnest-managed webcam stream via a plain-HTTP `CrowsnestCamera` driver, with a runtime-adjustable `SetCaptureInterval` command, mock camera path (dependency-free placeholder PPM image), and per-capture archiving to `logs/images/` alongside the usual JSONL event log. `CameraProtocol` is a single `capture() -> bytes` method, so Crowsnest is one implementation, not the whole abstraction, per the TODO's acceptance criteria. Frontend plugin (`devices/camera/capability/frontend/`) shows the live image plus an interval control. `rxn_bench_client.Camera` adds `snapshot()`/`save_snapshot()`/`set_capture_interval()`. Required extending the shared `gen_proto.py`/`gen_connections.py` generators with a `Binary` primitive wrapper (`bytes` -> SiLA's native `Binary` basic type) - the first non-Real/Boolean/SString primitive any device has needed; verified end-to-end against a live mock server (real gRPC subscribe + command call, not just unit tests). **Real Crowsnest wiring verified 2026-08-13** - the code's `crowsnest_base_url`/`crowsnest_snapshot_path` defaults (`http://sv08.local:8080`, ustreamer's `/snapshot`) don't match this bench's actual setup: `sv08.local` doesn't resolve (mDNS doesn't cross the subnet boundary, same root cause as `moonraker_fallback_host`), and Crowsnest/ustreamer isn't exposed on 8080 at all - Fluidd's nginx on the SV08 host proxies the webcam at `/webcam/snapshot` on port 80 instead. Fixed by adding `crowsnest_base_url: "http://192.168.10.2"` and `crowsnest_snapshot_path: "/webcam/snapshot"` to `~/.rxn_bench/machine.yaml`; confirmed both the on-demand `capture()` path (real 146KB JPEG, visually verified as an actual bench frame) and the periodic background capture that feeds `logs/images/` (first real archive landed ~30s after the service restart, matching the default `capture_interval_s`). |
| Backend capability-spec generator (`interfaces.py` from `<Feature>.capability.yaml`) | Done - see "Capability Spec Pattern" (§4). All 5 packages (gantry, ph_sensor, camera, dosing_pump, device_template) migrated; `feature.py` stays 100% hand-written everywhere, only `interfaces.py` + a `.capability.md` doc snapshot are generated. `make check-capability`/`make gen-capability` (`rxnbench/backend/Makefile`), wired into CI alongside `check-proto`. Surfaced two real pre-existing bugs while migrating: camera's `set_capture_interval` had no `CameraProtocol` backing, and gantry's `feature.py` called `calibrate_toolhead_tip`/`calibrate_toolhead_tip_z` on the controller despite neither ever being declared in `GantryControllerProtocol` - both fixed as part of the migration. Verified: full backend test suite (479 tests across all packages) unchanged, `make check-capability`/`check-proto` both pass, frontend `check-connections`/tests confirmed unaffected. |

---

## 6. Current Gaps

These are the active issues worth tracking now.

| Gap | Location | Priority | Notes |
|---|---|---:|---|
| Verify real pH I2C path on the Pi | `rxn_bench_ph/i2c_bus.py` + physical bench | Low | Superseded: the reference bench runs the pH probe over **UART**, not I2C (the EZO is wired to the Pi's GPIO 14/15 TX/RX and left in its default UART mode). The **UART** path (`AtlasScientificEZOUart` on `/dev/ttyAMA0` @ 9600) is verified against the physical EZO circuit as of 2026-07-13 - live pH readings confirmed on the deployed `rxn-bench-ph` service. The I2C driver remains complete and mock-tested but is no longer on this bench's runtime path, so verifying it against real I2C hardware is now low priority. |
| Migrate configs to pydantic | gantry config models | Medium | Gives validation, clearer errors, and JSON Schema export. |
| Push the split-out device repos to GitHub and repoint `.gitmodules` | `.gitmodules`, `rxn-bench-device-repos/` (currently local, sibling to this checkout) | High for the JOSS repo restructure | Each `devices/<name>/{capability,driver}` (or the earlier `{backend,frontend}` shape) is a submodule pointing at a local path today. CI's `submodules: true` checkout (`ci.yml`, `windows-installer.yml`) will not succeed until these are pushed somewhere reachable (presumably the RxnRover org) and `.gitmodules`/`git submodule set-url` are updated to match. Git history for these repos currently starts fresh at the split (single "Initial import" commit) - full history transplant via `git subtree split`/`git filter-repo` is an available follow-up, not done here. |
| Re-verify the offline bundle pipeline end-to-end after the capability/driver split | `rxnbench/backend/scripts/build_offline_bundle.sh`, `install_offline.sh` | Medium-High before the next Pi deployment | Both scripts were inspected and patched for the new paths (bundle's tar `--exclude` now matches `devices/*/capability/frontend`; `install_offline.sh` now runs `aggregate_toolheads.py` before `install_service.sh`; `install_service.sh`'s `WORKING_DIR`/`DRIVER_HOOK` point at `capability/backend`/`driver/backend`) and the reasoning was verified line-by-line (each driver package is a plain dependency of its capability, so a single `-e capability/backend` install still pulls the driver in via its own `[tool.uv.sources]` path entry, unchanged install invocation) - but the actual bundle build + a from-scratch offline install on real or simulated Pi hardware has not been re-run since the split, unlike the rest of this change (which was verified via `make test`/`make dist-check`). |
| Add TLS + authentication deployment guide | docs/config | Low until shared-network deployment | Bare, unauthenticated gRPC is acceptable for isolated bench development but not for a shared lab network. Note: Moonraker's own HTTP API on the Pi is itself unauthenticated by default, so network exposure bypasses *all* gantry safety logic (bounds, clearance, experiment lock) the moment this leaves an isolated bench network - TLS on the SiLA/gRPC layer alone would not close that hole. The experiment-lock token is a coordination mechanism, not authentication: any client on the network can still acquire the lock when it's free. |
| Verify sample-holder labware dimensions | `labware/6_well_sample_holder.yaml` (+ header comment in `3_well_sample_holder.yaml` still says "6-Well") | Medium | The 6-well file was scaffolded with standard 6-well *plate* dimensions as placeholders - caliper-verify spacing/offsets against the physical holder before running wells on it. The 15-well and 3-well holders already carry measured-looking values. |
| Verify `plate_height_mm` across all labware types | `labware/*.yaml` | Medium | New field (deck to plate top surface) added to every bundled labware file to drive dynamic safe clearance-travel height. All 6 are currently `well_depth_mm + ~3mm` estimates, not measured - caliper-verify before trusting them for collision safety, same as the existing well-geometry gap above. |
| Measure pH probe `tip_x` / `tip_y` | `toolheads/ph_probe/ph_probe_toolhead.yaml` | Low | Current values are still placeholders - the physical measurement itself hasn't happened. The guard is implemented: `ToolheadGeometry.geometry_validated` (default `True`, `False` for `ph_probe`) logs a warning on `set_toolhead()` and `GantryController.move_to_well()` refuses to run with a `UnvalidatedGeometryError` unless `override_unvalidated=True` is passed. Plain `move_to()`/`jog()` are unaffected - only well-targeted moves are gated. |
| Verify the dosing pump against the real EZO-PMP circuit | `rxn_bench_dosing_pump/atlas_scientific_uart_driver.py` + physical bench | Medium | **Serial port resolved 2026-08-04:** the bench Pi 5 runs `dtoverlay=uart2` (config.txt), which brings up UART2 on GPIO4/5 as `/dev/ttyAMA2` - confirmed against the real EZO-PMP (`?I,PMP,1.06`, `?STATUS`, and `PV,?` -> 11.99 V motor supply all responded correctly over that port). `install_service.sh` now sets `RXN_BENCH_PUMP_SERIAL_PORT=/dev/ttyAMA2` for the `pump` device automatically, so it no longer collides with the pH probe's `/dev/serial0`. **Concurrency bug found and fixed 2026-08-04:** the info/status smoke test surfaced a real race - `VolumeDispensed` and `Dispensing` are two separately-polled observable streams (1Hz each, `asyncio.to_thread`), plus any in-flight command, all sharing one unguarded serial port; interleaved writes/reads on real hardware produced garbled replies (`'D,100,'`, `'O'`, `'OK?-.0,0*'`). Fixed with a `threading.Lock` + `_transact()` atomic send/read helper on `EZOPumpCommandSet`, used by every command method. Re-verified with 30 concurrent calls across two threads against the real pump: zero errors. See the 2026-08-04 CHANGELOG `Fixed` entry. Still unconfirmed on hardware: the `*DONE` interrupt behaviour when a dispense completes mid-query (the emulator reproduces the ordering the driver guards against, but real firmware timing may differ), whether `Invert,?`/`P,?` reply exactly as the datasheet's tables show, and the real `DC,?` max rate. The pump also supports I2C (default address 103/0x67) as an alternative to UART; no I2C driver is written (deliberately, not speculatively). |
| Calibrate the dosing pump | physical bench | Medium | Volumes are nominal until a single-point calibration is done (`Dispense` a known amount, measure it, send `Calibrate(measured)`); the datasheet's ±1% accuracy assumes it. `MaxFlowRate` is only meaningful post-calibration, and the widget uses it to cap its rate input. |
| Tune camera image-log retention for the deployment's storage budget | `rxn_bench_camera/image_log.py`, `~/.rxn_bench/machine.yaml` | Medium | Default is `capture_interval_s=30`, 7-day retention on `logs/images/`; this can still add up to several GB on a Pi's SD card at higher capture rates. No pressure to change until a real bench session shows it's a problem. |
| Activate the X-gantry crossbar collision check on the bench | `~/.rxn_bench/machine.yaml` | Medium-High (safety) | The check is implemented and tested but **inert until configured**: `MachineConfig.crossbar_clearance_above_tip_mm` (crossbar underside height above the tip, in the workspace Z frame) and `crossbar_y_thickness_mm` (the bar's Y extent) are both `None` by default. `GantryController` refuses a well dock / `engage_tool` descent that would drive the full-X crossbar into a taller plate sharing the target's Y-row (`WorkspaceManager.max_top_in_y_band`); the X span is assumed full. The bar is also **visualized** in the workspace viewer's X/Z + Y/Z side views under "show more details" (`GetLimits` gained two trailing crossbar fields, still one SString). Needs the operator's two crossbar measurements written into `machine.yaml` to switch on (see the 2026-07-13 CHANGELOG entry). The gantry SiLA feature was also bumped **v0 -> v1** (`Gantry/v1`, matching pH/camera) - frontend and backend must be deployed together at the same version. |
| Windows installer - confirm the `.exe` artifact | `.github/workflows/windows-installer.yml` | Medium for TODO-AI.md §1.2 | A `windows-latest` workflow (tag `v*` / manual dispatch) installs Inno Setup, runs the PyInstaller onedir build + `copy_device_plugins.py` + `iscc packaging/installer.iss`, and uploads `Rxn-Bench-Setup-<version>.exe`. **First real run (2026-07-13) confirmed the Windows PyInstaller build works** - onedir build, plugin staging, and the frozen self-test all passed on the runner (the big unknown is answered). Only the `iscc` step failed, on a Git-Bash/MSYS quirk that rewrote the `/DMyAppVersion=` option into a path ("more than one script filename"); fixed by running that step in PowerShell. Re-run (new tag) still pending to confirm the installer `.exe` actually builds + uploads end-to-end. |
| Verify installer's auto-pin + multicast-route service on a from-scratch reinstall | `rxnbench/backend/scripts/install_offline.sh` (+ `install_service.sh`) | Medium | On the gatewayless bench network discovery silently fails despite healthy services, two independent causes (see the 2026-07-13 CHANGELOG entry): the CDK auto-detect advertises `127.0.0.1`, and multicast can't egress with no default route. Fixed: `install_offline.sh` auto-detects the host's primary IPv4 (`hostname -I`) and (a) pins `sila_server.hostname` via a `~/.rxn_bench/<device>.json` override (new `--advertise-ip <IP>` flag to `install_service.sh`; `--no-pin` opts out), and (b) when the multicast group isn't already routable, installs a boot-time `rxn-bench-mcast-route.service` oneshot (`ip route replace 224.0.0.0/4 dev <iface>`). Device systemd units now wait on `network-online.target` since they bind a specific IP. **Note:** `discovery.network_interfaces` is a no-op - the CDK connector (`unitelabs/cdk/connector.py`) never forwards the discovery config to its multicast socket, so `IP_MULTICAST_IF` is never set; the route is the only lever (confirmed empirically). The pin/route logic was validated in isolation and applied by hand to the live Pi (discovery confirmed working), but the full installer path hasn't been re-run end-to-end on a from-scratch reinstall yet. Repo config templates intentionally keep `hostname: "0.0.0.0"` - the correct *generic* default; the pin/route are deployment-time only. |
| Experiment script hangs forever on a dropped network link | `rxn_bench_client/client.py` (`RxnBenchClient.connect`), `sila2`'s `SilaClient` | Medium | Confirmed 2026-08-04: unplugging the operator machine's ethernet mid-run freezes the script indefinitely instead of erroring. Root cause: `sila2.client.SilaClient` builds its channel with plain `grpc.insecure_channel(target)` (no options), and `sila2.client.utils.call_rpc_function` never passes a per-call `timeout=`, so a call blocks forever on a connection that goes silent (no RST/FIN from an unplugged cable) - there's no deadline anywhere in the call path to catch. `bench.log()` was hardened the same day to skip a row it can't write (`OSError`) instead of raising, but that only helps once a call *returns*; it doesn't unblock a hung SiLA call. Fix requires gRPC channel keepalive options, which `SilaClient.__init__` doesn't expose (would need a scoped monkeypatch of `grpc.insecure_channel` around the `SilaClient(...)` construction in `connect()`). A client-only fix bounds the freeze to ~5 min by matching the SiLA servers' *default* (unconfigured) ping-abuse tolerance (`GRPC_ARG_HTTP2_MIN_RECV_PING_INTERVAL_WITHOUT_DATA_MS` = 5 min) - going faster than that requires also loosening server-side ping tolerance in all four device backends (gantry/ph/pump/camera) and redeploying+restarting every service on the Pi. Deliberately not implemented yet - pending a decision on which tradeoff (see chat 2026-08-04). |

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
- Keep each device self-contained as one `devices/<name>/{backend,frontend}` folder at the repo root (a "drop in or remove" unit), while the SiLA/gRPC machine-separation boundary and the uv-workspace/single-frontend-app mechanics stay exactly as before - this is a file-layout change, not an architecture change. `rxnbench/backend/` and `rxnbench/frontend/` hold the non-device-specific app/workspace machinery only.
- Keep shared connection lifecycle code in `connections/base.py`.
- Keep generated connection code next to the device it belongs to.
- Keep widgets handwritten.
- Keep workflows handwritten.
- Keep device discovery server-sourced through `SiLAService.GetImplementedFeatures`.
- Keep toolhead and labware definitions YAML/config-driven.
- Keep experiment scripts using `rxn_bench_client` rather than directly depending on frontend code.
- Keep the shared uv workspace venv for local dev/test only. Production deployment gives gantry and ph_sensor their own standalone venv each (via `scripts/install_service.sh`), so either service can be updated/restarted without affecting the other.
- Duplicate small utilities per device rather than extracting a shared common package. `rxn_bench_gantry/session_log.py` and `rxn_bench_ph/session_log.py` are functionally identical (byte-for-byte except one docstring word) - this is intentional, not drift to fix. Keeping each device's backend self-contained (no shared runtime dependency between otherwise-independent device packages) outweighs de-duplicating ~70 lines. (Build scripts are the exception: `rxnbench/backend/scripts/gen_proto.py` is one generator with a per-device manifest, because generated wire formats must not drift between devices.) This extends to *vendor protocol* code, not just utilities: `rxn_bench_dosing_pump` re-implements the Atlas EZO UART framing that `rxn_bench_ph` already has, because the two devices share a protocol *family* (Atlas EZO circuits) but not a command set - and importing across device packages would put the pH package on every machine running only the pump. The shape is copied (transport-agnostic command set + one transport class), the code is not.
- A shared-generator addition is preferred over a per-device carve-out when a device needs a wire type the generators don't cover yet. Two have been added this way: `Binary` (camera images) and `Integer` (the dosing pump's calibration status). Both are real SiLA basic types with a single obvious protobuf mapping, so they generalize; a device-specific escape hatch in `gen_proto.py` would not.
- Both drift checks (`make check-proto`, `make check-connections`) and all test suites now run in CI (`.github/workflows/ci.yml`) on every push/PR, in addition to being runnable locally before a PR.
- Experiment lock uses a **token**, not caller identity: `AcquireExperimentLock` returns a secret; state-changing commands take an optional `Token` parameter checked backend-side. The UI never sends a token (so it is locked out during runs, except Pause/Resume/Stop); `rxn_bench_client.Gantry` attaches its token automatically. This is coordination between cooperating clients, not authentication (see the TLS gap in §6).
- Plate/labware geometry is served by the gantry backend (`GetLabware`, YAML) and consumed by the frontend canvases and the experiment client. Never hardcode plate dimensions outside `rxn_bench_gantry/labware/*.yaml` - the frontend's former hardcoded table had already drifted ~9 mm from the backend on the 24-well plate. `PlateGeometry.plate_height_mm` is now part of that same single source of truth and drives `GantryController`'s clearance-travel math - a labware YAML's dimensions are never duplicated into a second, separately maintained safety constant. (Tests must also derive plate dimensions from `PlateGeometry`, not hardcode them - five `test_controller.py` tests hardcoding `96_well`/`24_well` numbers silently broke when the labware was re-measured; fixed to load from the source.)
- Workspace Z is a **3-layer decomposition**, each layer configurable at its natural scope: `WorkspaceConfig.deck_height_mm` (shared deck/workplate top height above Z=0, the bed) + `PlacedPlate.origin_z` (that plate's footprint/mount height *above the deck*) + labware `plate_height_mm` (the plate's own height) = the well opening Z. The shared deck lives in one workspace-level field so swapping decks is a one-line change instead of editing every plate. `deck_height_mm` defaults to 0 for backward compatibility (then `origin.z` alone is the resting-surface height above Z=0, as before it existed). The frontend re-derives this same sum from the workspace YAML independently (`workspace_loader.resolve_reference_plate_height` and the side views) rather than importing backend code.
- Multiple toolheads can be physically mounted at once; exactly one is *active* (its geometry drives targeting/bounds). Mount confirmations are per-head and survive activation switches - switching (`set_toolhead`) is a pure software change that preserves homing state, so scripts alternate between pre-confirmed heads without operator interaction. Homing invalidates on *physical* changes only (confirming/clearing a mount, removing a head) and only when the state actually changes (re-confirming is a no-op). Well-targeted moves require the active head to be confirmed mounted and geometry-validated; plain `move_to`/`jog` are ungated. The two frontend slots are selection presets over this model.
- Frontend plugins talk to servers **only** through their device connection (`connection.py` / generated base). No raw `grpc.insecure_channel` or hand-rolled protobuf in widgets - the last two violations (workspace loader's ad-hoc channels; pH/template varint helpers) were removed in this pass.
- Device repos and frontend plugin discovery are two separate concerns, kept orthogonal on purpose: whether a device's code lives in this checkout as a plain directory or a git submodule is a git-plumbing question (uv workspace members / editable path sources reference the same relative path either way, so the split required zero build-config changes beyond CI's checkout step); whether a device is *discovered* via entry points or the directory scan is a Python-packaging question, decided per device by whether it has a flat `devices/<name>/frontend/__init__.py` (directory-scanned) or a `src/rxn_bench_<name>_frontend/` package with its own `pyproject.toml` (entry-point-discovered). Don't conflate "split into its own repo" with "switch to entry points" - a device can be submoduled without migrating its discovery mechanism, and vice versa.
- Every backend device separates a **capability** (SiLA feature + Protocol interface, hardware-agnostic - `rxn_bench_<name>`) from a **driver** (the concrete implementation, plus its hardware CAD and toolhead config - `rxn_bench_<vendor>_driver`), registered under a `rxn_bench.<name>_drivers` entry-point group so the capability never imports a concrete driver. This is the backend mirror of the frontend's entry-points plugin pattern (§2) - same reasoning: a capability should be reusable by a different vendor's hardware with zero changes on the capability side. A mock only belongs in the capability package if it satisfies the Protocol directly with no vendor wire-protocol emulation (`MockPHSensor`, `MockCamera`, `MockMoonrakerClient`); a mock built on the real driver stack over a protocol emulator (`MockDosingPump(AtlasDosingPump)`, `MockI2CBus`, `MockEZOUart`) is driver-side, registered as its own entry point, not a capability-side import - don't assume `RXN_BENCH_MOCK=1` always resolves inside the capability package.

---

## 9. Platform Roadmap

**Long-term goal:** grow Rxn Bench from a single bench (gantry + pH) into more of an all-around laboratory control platform - many/heterogeneous devices, not just this one bench. This doesn't change anything in sections 1-8; the device-first layout, one-SiLA-server-per-device model, and mock/real hardware split already scale toward this goal without rework.

Near-term, in priority order:

1. **Workflow runner in `rxn_bench_client` - not a YAML DSL, a thin structural layer over plain Python scripts.** Experiment scripts stay arbitrary Python (loops, conditionals, numpy/pandas, adaptive logic) - that expressiveness is worth keeping, not replacing. What's missing is a lightweight decorator/context-manager per step that gives a `WorkflowRunner` enough structure to: retry/resume from the failed step instead of rerunning the whole script, know which devices a step touches before running it (so a future scheduler can avoid device contention), and record a structured per-step audit trail alongside the existing JSONL session logs. Design constraint: each step must carry an idempotency/side-effect flag, and resume-from-failed-step must default to requiring human confirmation before re-running or skipping a step - physical actions (dispensed liquid, a probe already lowered into a well) can't be rolled back the way a database transaction can. Pure Python, no new service or database; lives inside the existing client package. (MADSci itself does the analogous thing - YAML workflows plus an escape-hatch `ExperimentApplication` Python class - because pure declarative workflows aren't enough either.)
2. ~~**Prove the pattern with a real third device.**~~ Done - the camera device (TODO-AI.md §2.1, see §5) added only `devices/camera/{backend,frontend}` plus one shared-generator extension (the `Binary` primitive wrapper in `gen_proto.py`/`gen_connections.py`, needed because images are the first non-Real/Boolean/SString payload any device has sent - a generic addition, not a camera-specific carve-out). Nothing in `core/` or `device_registry.py` changed. The bar from this item is cleared; machine-vision work (error detection, run monitoring, workspace inspection, calibration assistance) can build on `CameraProtocol`'s raw `capture() -> bytes` without further abstraction changes.

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
