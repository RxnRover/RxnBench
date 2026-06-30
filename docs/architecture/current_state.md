# Automated Chem Bench — Architecture Review

**Date:** June 2026 (last updated June 29 2026)
**Reviewer:** Architectural analysis of commit `e7c34c9`; updated through frontend plugin restructure and rxnbench namespace rename (June 29 2026)
**Scope:** Full codebase review — all first-party Python source, YAML configs, and tooling

---

## Frontend Rebuild + Plugin Architecture — June 29 2026

*Replaces the previous non-functional `app.py` stub and flat `widgets/` layout.*

### What Changed

The frontend is now a fully functional PySide6 desktop application. The flat `widgets/` + `ui/` directories have been reorganised into a `core/` shell and a `devices/` plugin tree.

#### New directory layout

```
software/frontend/src/chem_bench_ui/
├── app.py                         ← entry point (was a 21-line stub; now launches full UI)
├── discovery.py                   ← SiLA mDNS + probe discovery
├── themes.py                      ← DARK/LIGHT palettes + build_qss(); widget_bg key added
├── sila_client.py / ph_client.py  ← gRPC stream clients
├── assets/                        ← app-wide assets (rxnbench_logo.png)
├── proto/                         ← motion_platform.proto + compiled _pb2.py
├── core/                          ← app shell — not a plugin
│   ├── main_window.py             ← QMainWindow; MDI canvas + Add Device tab
│   ├── server_browser.py          ← SiLA server scan/browse/connect cards
│   ├── device_registry.py         ← auto-discovers devices via devices.all_devices()
│   ├── generic_device.py          ← fallback widget for unrecognised SiLA servers
│   └── ui/                        ← main_window.ui / server_browser.ui / server_card.ui
└── devices/                       ← one sub-package per device type
    ├── __init__.py                ← all_devices() via pkgutil.iter_modules
    ├── gantry/
    │   ├── __init__.py            ← FEATURE_FRAGMENTS + create_widget()
    │   ├── widget.py              ← GantryWidget (PySide6)
    │   ├── workspace_loader.py    ← YAML workspace load/apply panel
    │   ├── experiment_panel.py
    │   ├── homing_dialog.py / toolhead_calibration_dialog.py
    │   ├── assets/                ← gantry-specific images
    │   └── ui/                    ← *.ui files for every gantry sub-panel
    └── ph_sensor/
        ├── __init__.py            ← FEATURE_FRAGMENTS + create_widget()
        ├── widget.py              ← PHSensorWidget (PySide6)
        └── ui/
```

#### Plugin contract

Each device package's `__init__.py` must export two things:

```python
FEATURE_FRAGMENTS: list[str]          # matched (case-insensitive) against SiLA feature identifiers
def create_widget(server, theme: dict) -> QWidget: ...
```

`devices/__init__.py` auto-discovers sub-packages at import time:

```python
import importlib, pkgutil

def all_devices():
    return [
        importlib.import_module(f".{name}", package=__name__)
        for _, name, ispkg in pkgutil.iter_modules(__path__)
        if ispkg
    ]
```

`core/device_registry.py` calls `all_devices()` — the hardcoded `REGISTRY` list is gone. Adding a new device = drop a new folder under `devices/` with the required exports. Zero changes to core.

### UI Features Implemented

| Feature | Details |
|---------|---------|
| Dual theme | `DARK` / `LIGHT` switchable at runtime via Settings → Theme menu |
| MDI canvas | `QMdiArea` floating sub-windows; one per connected device; resizable/movable |
| Server browser | mDNS scan + manual probe; classifies servers as Rxn Bench Known Devices vs unknown SiLA |
| Server cards | Rxn Bench logo injected for rxnbench devices; feature list; orange `+` add button |
| Gantry widget | Position display, XYZ jog, toolhead selector, homing, workspace YAML loader |
| pH sensor widget | Live pH reading chart, calibration controls, connection state dot indicator |
| Theme persistence | `set_theme()` on every widget restores connection-state visuals (e.g. green dot) |
| `widget_bg` key | New theme key (`#ffffff` light / `#1c2333` dark) for device panel surfaces, distinct from the MDI canvas (`bg_surface`) |
| Generic device | `GenericDeviceWidget` shown for recognised-but-unmapped SiLA servers |

### What Was Removed / Replaced

| Removed | Replaced by |
|---------|-------------|
| `app.py` stub (21 lines, no window) | Full `MainWindow` with MDI workspace + Add Device tab |
| `widgets/` flat directory | `core/` (shell) + `devices/` (plugins) |
| `ui/` flat directory | `core/ui/` + per-device `devices/<name>/ui/` |
| Hardcoded `REGISTRY` list in `device_registry.py` | `devices.all_devices()` dynamic discovery |
| `_FEATURE_REGISTRY` + `_on_features_discovered` tab injection | Per-device `FEATURE_FRAGMENTS` matched in `core/device_registry.py` |

---

## Feature Namespace Rename — June 29 2026

All SiLA feature identifier strings have been renamed from `/rxnbench/` to `/rxnbench/` across the entire codebase.

### What Changed

| Location | Before | After |
|----------|--------|-------|
| `discovery.py` — filter | `/rxnbench/` | `/rxnbench/` |
| `discovery.py` — property | `chembench_features` | `rxnbench_features` |
| `discovery.py` — signal | `chembench_server_found` | `rxnbench_server_found` |
| `core/server_browser.py` — variables | `chembench` | `rxnbench` |
| `devices/gantry/widget.py` | `FEATURE_ID = "edu.iastate.ames/rxnbench/Gantry/v0"` | `…/rxnbench/…` |
| `devices/gantry/workspace_loader.py` | `_GANTRY_BASE = "/sila2.…chembench…"` | `…rxnbench…` |
| `sila_client.py` / `ph_client.py` | identifier strings | `rxnbench` |
| `scripts/scan_sila.py` | `/rxnbench/` tag | `/rxnbench/` |
| **Backend** `chem_bench_gantry/feature.py` | `category="chembench"` | `category="rxnbench"` |
| **Backend** `chem_bench_ph/feature.py` | `category="chembench"` | `category="rxnbench"` |
| **Backend** `device_template/feature.py` | `category="chembench"` | `category="rxnbench"` |
| **Backend** `gantry/tests/test_feature_discovery.py` | identifier strings | `rxnbench` |
| **Backend** `gantry/scripts/gen_proto.py` | package name | `sila2.edu.iastate.ames.rxnbench.gantry.v0` |
| `proto/motion_platform.proto` | package name | `sila2.edu.iastate.ames.rxnbench.gantry.v0` |
| `proto/motion_platform_pb2.py` | compiled binary | recompiled from updated `.proto` |

The proto recompile was done with `grpcio-tools` from the backend uv workspace (frontend venv does not include `grpcio-tools`). The workflow is unchanged: `make gen-proto` in `software/backend/` regenerates and recompiles.

---

## Package Restructure — June 2026

*Replaces the previous monolithic `src/chem_bench/` package.*

### What Changed

The single `chem-bench` package has been split into three independently deployable Python packages, each its own uv workspace member under `software/backend/`:

| Package dir | Package name | Entry point | Port | Runs on |
|-------------|--------------|-------------|------|---------|
| `gantry/` | `chem-bench-gantry` | `chem-bench-gantry` | 50051 | Raspberry Pi |
| `ph_sensor/` | `chem-bench-ph` | `chem-bench-ph` | 50052 | Raspberry Pi |
| `client/` | `chem-bench-client` | *(library only)* | — | Backend machine |

The root `software/backend/pyproject.toml` is now a uv workspace root:

```toml
[tool.uv.workspace]
members = ["gantry", "ph_sensor", "client"]
```

### Why

- Each device will eventually live in its own repo. The package boundary enforces that isolation now — `chem_bench_gantry` has no import dependency on `chem_bench_ph` and vice versa.
- Per-device SiLA servers align with the UniteLabs CDK convention: one feature family per Connector process.
- Separate processes mean one device crashing (e.g. I2C hang on pH sensor) cannot take down the gantry.

### What Was Removed

- `software/backend/src/chem_bench/` — entire old monolithic package (deleted)
- `software/backend/tests/` — old test directory (tests migrated to `gantry/tests/`)
- `software/backend/scripts/gen_proto.py` — moved to `gantry/scripts/gen_proto.py`
- `software/backend/configs/` — now per-package (`gantry/configs/`, `ph_sensor/configs/`)

### Old → New Module Path Map

| Old path | New path |
|----------|----------|
| `chem_bench.features.gantry` | `chem_bench_gantry.feature` |
| `chem_bench.features.ph_sensor` | `chem_bench_ph.feature` |
| `chem_bench.io.gantry.gantry_controller` | `chem_bench_gantry.controller` |
| `chem_bench.io.gantry.motion_engine` | `chem_bench_gantry.motion_engine` |
| `chem_bench.io.gantry.homing_manager` | `chem_bench_gantry.homing_manager` |
| `chem_bench.io.gantry.toolhead_manager` | `chem_bench_gantry.toolhead_manager` |
| `chem_bench.io.gantry.workspace_manager` | `chem_bench_gantry.workspace_manager` |
| `chem_bench.io.gantry.moonraker_client` | `chem_bench_gantry.moonraker_client` |
| `chem_bench.io.gantry.mock_moonraker` | `chem_bench_gantry.mock_moonraker` |
| `chem_bench.io.gantry.homing_state` | `chem_bench_gantry.homing_state` |
| `chem_bench.io.gantry.moonraker_discovery` | `chem_bench_gantry.moonraker_discovery` |
| `chem_bench.io.labware.plate_geometry` | `chem_bench_gantry.plate_geometry` |
| `chem_bench.io.workspace.workspace_config` | `chem_bench_gantry.workspace_config` |
| `chem_bench.io.interfaces.motion` | `chem_bench_gantry.interfaces` |
| `chem_bench.io.toolheads.toolhead_config` | `chem_bench_gantry.toolhead_config` |
| `chem_bench.io.base_sensor` | `chem_bench_ph.base_sensor` |
| `chem_bench.io.base_driver` | `chem_bench_ph.base_driver` |
| `chem_bench.io.interfaces.ph_sensor` | `chem_bench_ph.interfaces` |
| `chem_bench.io.interfaces.enums` | `chem_bench_ph.enums` |
| `chem_bench.io.ph.atlas_scientific_driver` | `chem_bench_ph.atlas_scientific_driver` |
| `chem_bench.io.ph.atlas_ph_sensor` | `chem_bench_ph.atlas_ph_sensor` |
| `chem_bench.io.ph.mock_ph_sensor` | `chem_bench_ph.mock_ph_sensor` |
| `chem_bench.client` | `chem_bench_client.client` |

---

## Communication Layer Review

*Added after proto codegen migration (commits `970d2bf` → `41f1c81`, June 2026).*

### What Changed

The 120-line hand-coded varint/LEN codec in `sila_client.py` has been replaced with `grpcio-tools`-generated protobuf stubs. The new pipeline:

```
software/backend/gantry/src/chem_bench_gantry/feature.py
  └── dataclasses.fields(Position)      ← field order: [x, y, z]
  └── dataclasses.fields(ToolheadInfo)  ← field order: [active, name, ..., toolhead_mounted]
          │
          ▼
software/backend/gantry/scripts/gen_proto.py   (reads dataclasses only, no CDK internals)
          │  uv run python gantry/scripts/gen_proto.py
          ▼
software/frontend/src/chem_bench_ui/proto/motion_platform.proto
          │  python -m grpc_tools.protoc --python_out=...
          ▼
software/frontend/src/chem_bench_ui/proto/motion_platform_pb2.py
          │  imported as _mp in sila_client.py
          ▼
_mp.Subscribe_Position_Responses.FromString(bytes(msg))
_mp.Jog_Parameters().SerializeToString()
```

**Why `dataclasses.fields()` is the right source:** the CDK runtime (`Structure.encode`) enumerates `dataclasses.fields()` in definition order to assign field numbers (`enumerate(elements.items(), start=1)`). The generator uses the same source, so field numbers in the proto are structurally guaranteed to match the CDK wire format as long as field definition order is preserved.

### What Was Removed

| Removed | Replaced by |
|---------|-------------|
| `_varint(n)` | `SerializeToString()` |
| `_read_varint(buf, pos)` | `FromString(bytes(msg))` |
| `_len_fields(buf)` | `FromString(bytes(msg))` |
| `_decode_real(buf)` | `.x.value`, `.y.value`, etc. |
| `_decode_bool(buf)` | `.active.value`, etc. |
| `_decode_string(buf)` | `.name.value`, `.State.value`, etc. |
| `_decode_position(data)` | `_mp.Subscribe_Position_Responses.FromString(bytes(msg))` |
| `_decode_state(data)` | `_mp.Subscribe_State_Responses.FromString(bytes(msg))` |
| `_decode_toolhead_info(data)` | `_mp.Subscribe_ToolheadInfo_Responses.FromString(bytes(msg))` |
| `_encode_real_field(value, field_num)` | `params.x.value = x` |
| `_encode_xyz(x, y, z)` | `_mp.Jog_Parameters()` / `_mp.MoveTo_Parameters()` |
| `_encode_string_field(value, field_num)` | `_mp.SetToolhead_Parameters()` |

### Bug Fixed During Migration

`_stream_saved_state` always decoded `has_saved_state` as `False`. The old decoder used `_len_fields` on the Boolean message inner content. `_len_fields` only captures LEN (wire-type 2) fields; the Boolean inner field is a VARINT (wire-type 0). The VARINT was silently skipped. The generated stub decodes it correctly.

### Drift Protection

`make check-proto` (in `software/backend/Makefile`) runs the generator and diffs the output against the committed `.proto`. It fails if they diverge. Run before every commit that changes backend dataclass field order.

```
make check-proto   # verify (CI)
make gen-proto     # regenerate + recompile (development)
```

---

## Interface Architecture Review

*Added after hardware abstraction interface migration.*

### New Files

| File | Contents |
|------|----------|
| `gantry/src/chem_bench_gantry/interfaces.py` | `MotionClientProtocol`, `GantryControllerProtocol` |
| `ph_sensor/src/chem_bench_ph/interfaces.py` | `PHSensorProtocol` |

All protocols use `typing.Protocol` (structural typing) and are `@runtime_checkable`.

`CameraClientProtocol` has not yet been migrated to the new package structure — camera support is Phase 2.

### Dependency Improvements

#### Motion stack (before → after)

**Before:**
```
MotionPlatform (SiLA)  →  MotionPlatformController (concrete)
                               └─ MoonrakerClient (concrete, imported at module level)
                               └─ MockMoonrakerClient (structurally compatible but unenforced)
```

**After:**
```
Gantry (SiLA feature)  →  GantryControllerProtocol  ←  GantryController
                               MotionClientProtocol  ←  MoonrakerClient
                                                     ←  MockMoonrakerClient
```

Key changes:
- `GantryController` no longer imports `MoonrakerClient`. The concrete client is injected by `server.py`, which owns the wiring decision.
- `MockMoonrakerClient` divergence is now statically detectable: adding a method to `MoonrakerClient` without adding it to `MockMoonrakerClient` will surface as a type error against `MotionClientProtocol`.

#### pH stack (before → after)

**Before:**
```
PHSensor (SiLA)  →  AtlasPHSensor (concrete Atlas-specific class)
```

**After:**
```
PHSensor (SiLA)  →  PHSensorProtocol  ←  AtlasPHSensor
```

Key change: `PHSensor.__init__` now accepts any object with `read()`, `calibrate()`, and `slope()`. A future pH probe can be wired in without touching the feature.

### Remaining Coupling

| Item | Location | Notes |
|------|----------|-------|
| `CalibrationPoint` enum is pH-specific | `chem_bench_ph/enums.py` | Now correctly co-located with pH code after package split. |
| `GantryController` still returns concrete `ToolheadGeometry` dataclass | `chem_bench_gantry/interfaces.py:get_toolhead` | Acceptable — `ToolheadGeometry` is a pure data class. |
| No mock I2C bus — `PHSensor` still cannot run in mock mode end-to-end | `chem_bench_ph/server.py` | Needs a `MockI2CBus` before the sensor chain can be exercised without hardware. Phase 2 item. |

---

## Table of Contents

1. [Current Architecture](#current-architecture)
2. [Dependency Graph](#dependency-graph)
3. [Architectural Strengths](#architectural-strengths)
4. [Architectural Weaknesses](#architectural-weaknesses)
5. [Technical Debt](#technical-debt)
6. [Risks](#risks)
7. [Recommended Migration Order](#recommended-migration-order)
8. [Capability-Based Architecture Assessment](#capability-based-architecture-assessment)
9. [AI-Assisted Device Onboarding Assessment](#ai-assisted-device-onboarding-assessment)
10. [Month-Long Implementation Plan](#month-long-implementation-plan)
11. [Dynamic Discovery Architecture](#dynamic-discovery-architecture)
12. [Remaining Hardcoded Components](#remaining-hardcoded-components)
13. [Path Toward Metadata-Driven UI](#path-toward-metadata-driven-ui)
14. [Path Toward AI-Assisted Device Onboarding](#path-toward-ai-assisted-device-onboarding)

---

## Current Architecture

### System Topology

```
Operator Machine (Linux/Mac/Win)          Raspberry Pi                        Sovol SV08
──────────────────────────────────        ──────────────────────────────────  ─────────────────
chem_bench_ui (PySide6 + gRPC)            chem-bench-gantry :50051            H616 ARM (Linux)
  SilaClient (grpcio stubs)               ├─ Gantry (SiLA feature)  ────────> Moonraker :7125
  ├─ raw gRPC :50051 (gantry)             │    └─ GantryController               └─ Klipper
  └─ raw gRPC :50052 (pH)                 │         └─ MoonrakerClient              └─ MCU
      └─ motion_platform_pb2              │
                                          chem-bench-ph :50052
  experiment_script.py                    └─ PHSensor (SiLA feature)
    └─ ChemBenchClient                         └─ AtlasPHSensor (mock or real I2C)
         (chem_bench_client)
         connects to both servers         Persistent state (~/.chem_bench/)
                                          ├─ homing_state.json
                                          ├─ workspace.yaml
                                          └─ machine.yaml
```

Two separate SiLA server processes run on the Raspberry Pi — one per device. The frontend and experiment scripts connect to both. The SV08 runs Moonraker on its onboard H616 SoC; the gantry server drives it over HTTP.

### Module Map

#### Gantry Package (`software/backend/gantry/src/chem_bench_gantry/`)

*Flat layout — no `io/` nesting. The package IS the gantry.*

| File | Purpose |
|------|---------|
| `server.py` | `create_app()` factory. Loads `MachineConfig`, discovers Moonraker, wires `GantryController` into the `Gantry` SiLA feature. Activates `MockMoonrakerClient` under `CHEM_BENCH_MOCK=1`. |
| `_cli.py` | `chem-bench-gantry` console script. Searches `~/.chem_bench/gantry.json` then `./configs/gantry.json`, then shims into `unitelabs.cdk.cli.connector`. |
| `feature.py` | SiLA2 Gantry feature. Defines `Position` and `ToolheadInfo` dataclasses (source of truth for proto generation). ObservableProperties: `Position`, `State`, `ToolheadInfo`, `HasSavedState`. All motion, homing, toolhead management, and workspace commands. |
| `interfaces.py` | `MotionClientProtocol`, `GantryControllerProtocol`. Structural protocols for hardware injection and mock seams. |
| `controller.py` | `GantryController`. Thin orchestrator: cross-subsystem calculations only (`_safe_clearance_z`, `_check_bounds`, offset compensation). Delegates to `ToolheadManager`, `HomingManager`, `MotionEngine`, `WorkspaceManager`. Satisfies `GantryControllerProtocol`. |
| `toolhead_manager.py` | `ToolheadManager`. Active toolhead config, mount state, `sensor_type`. Hardware agnostic — loads from YAML. |
| `homing_manager.py` | `HomingManager`. Axis limits, manual/auto homing state machine, kinematic-reset jog trick, JSON persistence. |
| `motion_engine.py` | `MotionEngine`. Safe clearance travel sequence (raise → XY → lower). Depends only on `MotionClientProtocol`. |
| `workspace_manager.py` | `WorkspaceManager`. Loads `WorkspaceConfig` YAML. Resolves well labels to world-space XYZ. Applies plate orientation (`standard` / `rotated_90`). Persists last-used workspace to `~/.chem_bench/workspace.yaml`; auto-restores on startup. |
| `moonraker_client.py` | Synchronous HTTP client for Moonraker REST API (port 7125). |
| `mock_moonraker.py` | In-memory drop-in. Activated via `CHEM_BENCH_MOCK=1`. |
| `moonraker_discovery.py` | Parallel mDNS + IPv6 link-local scan. Returns first responding host. |
| `homing_state.py` | JSON persistence of calibrated axis limits in `~/.chem_bench/homing_state.json`. |
| `toolhead_config.py` | `ToolheadConfig` + `ToolheadGeometry` dataclasses. `sensor_type: str \| None`. |
| `plate_geometry.py` | `PlateGeometry` frozen dataclass. ANSI/SLAS uniform-spacing well plates. `well_position(label)` → `(x, y)` in mm. `load(name)` / `list_available()` from bundled `labware/` directory. |
| `workspace_config.py` | `WorkspaceConfig` frozen dataclass + YAML loader. `PlacedPlate`, `Orientation` enum. |
| `machine_config.py` | `MachineConfig` dataclass. Loads from `~/.chem_bench/machine.yaml`; falls back to built-in defaults. |
| `errors.py` | `MotionLimitError`. |
| `labware/96_well_standard.yaml` | ANSI/SBS 96-well standard (9 mm pitch, 8×12, 10.67 mm depth). |
| `labware/24_well_standard.yaml` | ANSI/SBS 24-well standard (19.3 mm pitch, 4×6, 17.4 mm depth). |
| `toolheads/ph_probe/ph_probe_toolhead.yaml` | Real toolhead config: 44×25 mm footprint, 110 mm tip depth, 25 mm engage depth. `sensor_type: ph`. |
| `workspace/definitions/_workspace_template.yaml` | Template for new workspace definitions. |

#### pH Sensor Package (`software/backend/ph_sensor/src/chem_bench_ph/`)

| File | Purpose |
|------|---------|
| `server.py` | `create_app()` factory. Registers `PHSensor` (mock or real). |
| `_cli.py` | `chem-bench-ph` console script. |
| `feature.py` | SiLA2 PHSensor feature. ObservableProperty: `Ph`. Commands: `Calibrate`, `ReadSlope`. |
| `interfaces.py` | `PHSensorProtocol`. Three-method interface: `read()`, `calibrate()`, `slope()`. |
| `atlas_ph_sensor.py` | `AtlasPHSensor(BaseSensor)`. pH-specific logic (calibration, slope, temperature compensation). |
| `atlas_scientific_driver.py` | `AtlasScientificEZO`. Raw EZO I2C command set — no pH logic. |
| `base_sensor.py` | `BaseSensor` ABC + `SensorReading` dataclass. |
| `base_driver.py` | `AbstractI2CDriver` ABC. Send/read/delay pattern over I2C. |
| `mock_ph_sensor.py` | `MockPHSensor`. Returns fixed pH 7.00, no-op calibration. |
| `enums.py` | `CalibrationPoint` enum. |

#### Client Package (`software/backend/client/src/chem_bench_client/`)

| File | Purpose |
|------|---------|
| `client.py` | `ChemBenchClient`. Blocking wrapper around two `sila2.SilaClient` instances (gantry :50051, pH :50052). Used in experiment scripts that run on the backend machine. Exposes common operations as Python methods; raw feature access available via `bench.sila["gantry"]`. |

#### Frontend (`software/frontend/src/chem_bench_ui/`)

*Fully rebuilt as of June 29 2026. Plugin architecture replaces the previous flat `widgets/` layout.*

**Core files:**

| File | Purpose |
|------|---------|
| `app.py` | Entry point. Launches `MainWindow` with light theme. |
| `discovery.py` | SiLA mDNS discovery + blocking scan. `DiscoveredServer.rxnbench_features` filters `/rxnbench/` identifiers. `SilaDiscovery.rxnbench_server_found` signal. |
| `sila_client.py` | gRPC channel management, `grpcio-tools`-generated stub codec, Qt signals for position/state/toolhead/connection, background streaming threads. |
| `ph_client.py` | gRPC client for pH server. |
| `themes.py` | `DARK`/`LIGHT` color palettes as dicts. `build_qss(t)` generates QSS. Key `widget_bg` distinguishes device panel surfaces from the MDI canvas. |
| `proto/motion_platform.proto` | Proto3 source. Package: `sila2.edu.iastate.ames.rxnbench.gantry.v0`. Regenerate with `make gen-proto`. |
| `proto/motion_platform_pb2.py` | Compiled stubs. Regenerate with `make gen-proto`. |
| `proto/sila_service_pb2.py` | Compiled stubs for `SiLAService.GetImplementedFeatures`. |

**Core shell (`core/`):**

| File | Purpose |
|------|---------|
| `main_window.py` | `MainWindow`. QMdiArea canvas tab + Add Device tab. Theme switcher. Propagates `set_theme()` to all open panels. |
| `server_browser.py` | `ServerBrowserDialog`. mDNS scan, manual probe, server cards. Emits `device_requested(DiscoveredServer)`. |
| `device_registry.py` | `is_recognized()` / `panel_for()`. Calls `devices.all_devices()` — no hardcoded device list. |
| `generic_device.py` | Fallback `QWidget` for recognised-but-unmapped SiLA servers. |

**Device plugins (`devices/`):**

| Package | FEATURE_FRAGMENTS | Key files |
|---------|-------------------|-----------|
| `devices/gantry/` | `Gantry`, `LinearMotion`, `XYZStage`, `PositioningXY`, `AxisSystem` | `widget.py`, `workspace_loader.py`, `experiment_panel.py`, `homing_dialog.py`, `toolhead_calibration_dialog.py` |
| `devices/ph_sensor/` | `PHSensor`, `PHMeasurement`, `pHController`, `PhMeter`, `PotentialMeasure` | `widget.py` |

### Communication Layer

| Layer | Transport | Details |
|-------|-----------|---------|
| Frontend → Gantry server | gRPC (insecure, port 50051) | Raw `grpc.Channel` with `grpcio-tools`-generated stubs (`motion_platform_pb2`). ObservableProperties → `unary_stream`. Commands → `unary_unary`. |
| Frontend → pH server | *(not yet wired)* | pH not yet connected in `sila_client.py`. Planned Phase 2. |
| Experiment scripts → Both servers | `sila2.SilaClient` (insecure) | `ChemBenchClient` wraps both; no pre-compiled stubs needed — `sila2` fetches FDL from server at connect time. |
| Backend → SV08 | HTTP REST (port 7125) | `requests.post("/printer/gcode/script")` blocks until Klipper finishes. |
| SV08 internal | Serial (ttyS3) | H616 → MCU for real-time stepper pulses. Transparent to this codebase. |
| Discovery (Moonraker) | mDNS + IPv6 | `_moonraker._tcp.local.` via zeroconf + fe80:: neighbor probe in parallel. |
| Discovery (SiLA) | Manual | Operator enters hostname in the connection bar. |

### Infrastructure

| Component | Details |
|-----------|---------|
| Backend runtime | Python 3.12, `uv` workspace, two systemd services (one per device) |
| Gantry deps | `unitelabs-cdk`, `requests>=2.31.0`, `pyyaml>=6.0`, `zeroconf>=0.131.0`; dev: `grpcio-tools>=1.60.0`, `pytest>=8.0` |
| pH sensor deps | `unitelabs-cdk`; optional `rpi = ["smbus2>=0.4.3"]` |
| Client deps | `sila2>=0.14.0` |
| Frontend runtime | Python 3.12, `uv`, started via `chem-bench-ui` console script |
| Frontend dependencies | `PySide6`, `grpcio>=1.60.0`, `protobuf>=6.33.5`, `zeroconf` |
| SiLA CDK version | `unitelabs-cdk==0.11.2`, `unitelabs-sila==0.8.0` |
| Gantry config | `gantry/configs/gantry.json` (port 50051, UUID `a9a1052f`) |
| pH config | `ph_sensor/configs/ph_sensor.json` (port 50052, UUID `c1876353`) |

---

## Dependency Graph

```
chem_bench_ui.app  (stub — frontend rebuild pending)
  └── SilaClient
        ├── grpc.Channel ──────────────────────────────────→ chem-bench-gantry :50051
        └── motion_platform_pb2 (grpcio-tools generated)
              └── derives from motion_platform.proto
                    └── generated by gantry/scripts/gen_proto.py
                          └── dataclasses.fields(Position, ToolheadInfo)
                                from chem_bench_gantry.feature

experiment_script.py
  └── ChemBenchClient (chem_bench_client)
        ├── sila2.SilaClient ──────────────────────────────→ chem-bench-gantry :50051
        └── sila2.SilaClient ──────────────────────────────→ chem-bench-ph :50052

chem_bench_gantry.server  (app factory for gantry server)
  ├── MachineConfig.load() ────────────────────────────→ ~/.chem_bench/machine.yaml (or defaults)
  ├── Connector (unitelabs-cdk)
  └── Gantry feature (chem_bench_gantry.feature)
        └── GantryController  (satisfies GantryControllerProtocol)
              ├── ToolheadManager ──────────────────────→ toolheads/*/name_toolhead.yaml
              │     sensor_type: str | None
              ├── HomingManager
              │     ├── MotionClientProtocol
              │     └── homing_state ─────────────────→ ~/.chem_bench/homing_state.json
              ├── MotionEngine
              │     └── MotionClientProtocol
              │           ├── MoonrakerClient ─────────→ SV08 Moonraker :7125
              │           │     └── requests.post/get      └─ Klipper → MCU → motors
              │           └── MockMoonrakerClient (CHEM_BENCH_MOCK=1)
              └── WorkspaceManager
                    ├── WorkspaceConfig ──────────────→ workspace/definitions/*.yaml
                    │   └── auto-restore ─────────────→ ~/.chem_bench/workspace.yaml
                    └── PlateGeometry ────────────────→ labware/*.yaml

chem_bench_ph.server  (app factory for pH server)
  ├── Connector (unitelabs-cdk)
  └── PHSensor feature (chem_bench_ph.feature)
        ├── AtlasPHSensor → AtlasScientificEZO → smbus2.SMBus(1)  (real hardware)
        └── MockPHSensor  (CHEM_BENCH_MOCK=1)
```

---

## Architectural Strengths

**1. Per-device process isolation**
Each device runs as a separate SiLA server process. A pH sensor I2C hang cannot block gantry motion. Devices can be restarted independently. The boundary also prepares for the eventual one-device-per-repo split.

**2. Clean three-layer I/O stack**
Driver → Sensor → Feature, each with a single responsibility. `AtlasScientificEZO` knows only I2C bytes. `AtlasPHSensor` knows pH chemistry and the `BaseSensor` contract. `PHSensor` knows only SiLA endpoints and delegates everything else.

**3. Config-driven hardware registration**
Toolheads and well plates are YAML files in named subdirectories. Adding a new toolhead requires zero Python changes — drop in a folder matching the schema and it appears in `ListToolheads`.

**4. Structural mock seam**
`GantryController` accepts any `client` object with the right methods. `MockMoonrakerClient` is a complete in-memory drop-in. Development and CI can run the full SiLA server without physical hardware via `CHEM_BENCH_MOCK=1`.

**5. Session persistence**
Calibrated axis limits survive a clean shutdown via `homing_state.json`. Workspace layout auto-restores from `workspace.yaml` on startup regardless of how the server stopped.

**6. Dynamic device panel injection**
`devices.all_devices()` + `core/device_registry.py` selects the correct widget for each discovered server based on `FEATURE_FRAGMENTS`. Adding a new device requires only a new `devices/<name>/` package — no edits to core.

**7. `BaseSensor` — sensor identity and reading envelope**
`BaseSensor` provides `sensor_id`, `display_name`, `description`, and the `SensorReading` timestamped dataclass. Capability metadata is owned by the CDK layer — the correct place for AI-assisted onboarding since it operates at the protocol layer clients consume.

**8. Moonraker auto-discovery**
mDNS and IPv6 link-local probes run in parallel. The backend finds the SV08 without IP configuration for both WiFi and direct-cable topologies.

**9. Toolhead-aware bounds checking**
`_check_bounds` applies footprint half-widths and tip Z offset. Enforced in the controller, not left to callers.

**10. Safe clearance travel**
`move_to` always raises Z to `clearance_z` (adjusted for tip length) before XY travel, then lowers to the target Z. An invariant in `GantryController`, not a convention.

**11. Homing state machine with manual mode**
The kinematic pre-reset trick in `jog()` during manual homing enables axis limit discovery with a toolhead mounted, working around Klipper's position bounds.

---

## Architectural Weaknesses

**1. ~~`PHSensor` feature is coupled to the concrete implementation class~~ FIXED**
`PHSensor` now accepts `PHSensorProtocol`. Any sensor satisfying `read()`, `calibrate()`, `slope()` can be used without touching the feature.

**2. ~~`MoonrakerClient` has no enforced interface contract~~ FIXED**
`MotionClientProtocol` defines the full nine-method surface. Divergence between `MoonrakerClient` and `MockMoonrakerClient` is now statically detectable.

**3. ~~Blocking synchronous I/O in async SiLA handlers~~ FIXED**
All `Gantry` handlers use `await asyncio.to_thread(...)` for every call reaching `MoonrakerClient`.

**4. ~~Backend is a 2000+ line monolith~~ FIXED**
Split into three packages (`chem_bench_gantry`, `chem_bench_ph`, `chem_bench_client`) with flat module layout in each. See Package Restructure section above.

**5. ~~Hand-coded protobuf in the frontend~~ FIXED**
`sila_client.py` now uses `grpcio-tools`-generated stubs. Field numbers derived from `dataclasses.fields()` in `gen_proto.py`. Drift detected by `make check-proto`.

**6. Frontend not yet connected to pH server**
`sila_client.py` connects only to the gantry server. pH readings are accessible to experiment scripts via `ChemBenchClient` but not yet visible in the UI. Phase 2 item.

**7. No TLS in the production config**
Both server configs have `"tls": false`. Acceptable for isolated development; requires a plan before shared-network lab deployment.

**8. I2C bus is never instantiated**
The path from the Raspberry Pi's I2C bus to `AtlasPHSensor` is fully designed but the `smbus2.SMBus(1)` call that wires it up is absent from `chem_bench_ph/server.py`. There is no mock I2C bus for development either.

**9. `install_service.sh` is stale**
`gantry/scripts/install_service.sh` references the old `chem_bench.__main__:create_app` entry point and installs a single `chem-bench` service. The split architecture requires two separate systemd unit files (`chem-bench-gantry.service`, `chem-bench-ph.service`). Needs rewriting before any lab deployment.

---

## Technical Debt

| Item | Location | Severity |
|------|----------|----------|
| pH probe `tip_x`/`tip_y` not yet measured — zeros used | `chem_bench_gantry/toolheads/ph_probe/ph_probe_toolhead.yaml` | Low |
| Camera support absent — no package, no feature, no client | — | Low (Phase 2) |
| `install_service.sh` hardcodes old monolith entry point | `gantry/scripts/install_service.sh` | **Medium** — will silently fail on deployment |
| `install.sh` references old `chem-bench` entry point | `software/backend/install.sh` | **Medium** — broken on fresh install |
| ~~Frontend `app.py` is a non-functional stub~~ **FIXED** — full UI rebuilt | — | Resolved |
| ~~Frontend not wired to pH server~~ **FIXED** — `ph_client.py` + `PHSensorWidget` added | — | Resolved |
| ~~No workspace or labware UI on frontend~~ **FIXED** — `workspace_loader.py` + gantry canvas panel | — | Resolved |
| Proto stubs committed as generated code; `make check-proto` guards drift | `proto/motion_platform_pb2.py` | Low |
| ~~PHSensor feature not registered~~ **FIXED** — `MockPHSensor` added; `server.py` registers `PHSensor` in both mock and real paths | — | Resolved |
| ~~Machine axis limits hardcoded~~ **FIXED** — `MachineConfig` loads from `~/.chem_bench/machine.yaml` | — | Resolved |
| ~~`sensor_type` on wrong layer~~ **FIXED** — moved to `ToolheadConfig` | — | Resolved |
| ~~Backend monolithic package~~ **FIXED** — split into `chem_bench_gantry`, `chem_bench_ph`, `chem_bench_client` | — | Resolved |

---

## Risks

| Risk | Location | Impact | Likelihood |
|------|----------|--------|------------|
| Proto version skew — `motion_platform_pb2.py` compiled with `grpcio-tools==1.81.1` / `protobuf==6.33.6`. Upgrading without regenerating stubs causes import-time failures. | `proto/motion_platform_pb2.py` | Low — loud, caught at import | Rare |
| Observable Command response streams not consumed — `MoveTo` and `Jog` errors mid-move are silently discarded | `sila_client.py` | Low — frontend only sees gRPC status errors | Low |
| No TLS — bare gRPC on any network the Pi is on | `gantry/configs/gantry.json`, `ph_sensor/configs/ph_sensor.json` | Low in isolated lab, High if shared | Context-dependent |
| `ChemBenchClient` experiment scripts run arbitrary Python server-side with no auth | `chem_bench_client/client.py` | Low on isolated lab network; High if network is shared | Context-dependent |
| ~~Blocking `requests.post()` in `async def` SiLA handlers~~ **FIXED** | — | Resolved | — |
| ~~Homing state saved with default limits~~ **FIXED** | — | Resolved | — |
| ~~Ghost threads on rapid reconnect~~ **FIXED** | — | Resolved | — |
| ~~`MockMoonrakerClient` can silently diverge~~ **FIXED** | — | Resolved | — |
| ~~PHSensor imports concrete class~~ **FIXED** | — | Resolved | — |
| ~~Hand-coded protobuf field numbers~~ **FIXED** | — | Resolved | — |

---

## Recommended Migration Order

### Phase 1 — Interface contracts and async correctness (Week 1)

1. ✅ **Define `MotionClientProtocol` and `GantryControllerProtocol`** — done. Both live in `chem_bench_gantry/interfaces.py`.
2. ✅ **Fix blocking I/O** — done. All `MoonrakerClient` calls wrapped in `await asyncio.to_thread(...)`.
3. ✅ **Decouple `PHSensor` from concrete class** — done. `PHSensor.__init__` accepts `PHSensorProtocol`.
4. ✅ **Expose `SilaClient.host` as a public property** — done.

### Phase 2 — Complete the sensor chain (Week 1-2)

5. **Wire up `AtlasPHSensor` in `chem_bench_ph/server.py`** — add `smbus2.SMBus(1)` instantiation and mock I2C bus under `CHEM_BENCH_MOCK=1`.
6. **Add mock I2C bus** — a `MockI2CBus` alongside `MockMoonrakerClient` so the full feature set works in mock mode without hardware.
7. **Connect pH server in frontend `sila_client.py`** — wire pH observables to Qt signals.
8. **Fix `install.sh` and `install_service.sh`** — update both for the two-server architecture.

### Phase 3 — Well plate workflow layer (Week 2)

9. ✅ **WorkspaceManager + PlateGeometry** — done. `load_workspace_yaml`, `move_to_well` SiLA commands implemented.
10. ✅ **Read axis limits from the server** — done. `GetLimits` SiLA command; hardcoded constants removed from frontend.
11. **Expose plate overlay in the frontend** — plate footprint and well grid on `PositionGrid`.

### Phase 4 — Frontend decomposition (Week 2-3)

12. ✅ **Split backend** — done. Three packages: `chem_bench_gantry`, `chem_bench_ph`, `chem_bench_client`.
13. ✅ **Add pytest scaffold** — done. 56 smoke tests in `gantry/tests/`. Run with `make test-gantry`.
14. ✅ **Rebuild frontend `MainWindow`** — done. Full PySide6 UI with MDI canvas, server browser, gantry + pH panels, dual themes, plugin device architecture.

### Phase 5 — Metadata-driven UI foundation (Week 3)

15. **Add `DeviceInfo` SiLA feature** — returns structured JSON describing all registered features, toolhead list, and plate list.
16. ✅ **Migrate feature discovery to server-sourced** — `SiLAService.GetImplementedFeatures` replaces the `_KNOWN_FEATURES` probe loop.
17. **Migrate configs to `pydantic` models** — schema validation, JSON serialization, AI-verifiable configs.

### Phase 6 — AI onboarding scaffold (Week 4)

18. **Define JSON manifest schema** — versioned JSON Schema per device type.
19. **Add `OnboardingFeature` SiLA service** — accepts JSON device description, validates, writes config, hot-reloads feature registry.
20. **TLS config guide** — document cert generation and `config.json` changes for lab deployment.

---

## Capability-Based Architecture Assessment

The system is at an early stage of capability-based design.

| Principle | Status | Gap |
|-----------|--------|-----|
| Toolheads declare physical geometry | ✅ YAML configs, YAML-driven | Geometry only; no electrical/protocol capability declared |
| Sensors self-describe via CDK decorators | ✅ CDK handles this at the SiLA layer | FDL/feature introspection not yet consumed by the frontend |
| UI adapts to discovered features | ✅ `device_registry.panel_for()` selects widget from plugin `FEATURE_FRAGMENTS` | Server-driven via `SiLAService.GetImplementedFeatures`; widget content still hand-authored per device |
| New instruments require minimal code | ✅ Backend: YAML drop-in for toolheads, new package for new devices | Frontend: drop a new `devices/<name>/` package with `FEATURE_FRAGMENTS` + `create_widget()` — zero changes to core |
| Workflows depend on capabilities, not hardware | ❌ Not yet | No workflow layer; SiLA commands are raw hardware operations |
| Runtime capability registry | ❌ Not yet | Devices enumerated at startup in `server.py`; no runtime negotiation |

---

## AI-Assisted Device Onboarding Assessment

### Existing foundations (strong)

- The CDK's FDL generation (`@sila.ObservableProperty`, `@sila.UnobservableCommand`, etc.) produces the machine-readable feature description at the protocol layer.
- YAML-driven `ToolheadConfig` and labware definitions are easy for an AI to generate from datasheet measurements.
- The Driver → Sensor → Feature separation means an AI can target the correct abstraction level.
- The mock infrastructure means an AI-generated driver can be tested in software before hardware is connected.
- The per-device package structure means an AI can generate a complete new device package (following `chem_bench_ph` as the template) without touching existing code.

### Gaps to close

1. **No pydantic validation** — AI-generated YAML configs cannot be automatically validated before use.
2. **No runtime schema access** — The SiLA FDL XML is not accessible at runtime for parameter introspection.
3. **No device registry endpoint** — Currently requires a developer to write Python, drop in a YAML, and restart the server.
4. **No structured parameter schemas on SiLA commands** — Units and valid ranges are enforced in Python logic but not declared in a machine-readable way.

### Recommended path

The most impactful next step for AI onboarding is **pydantic models for configs** (Phase 5). Once `ToolheadConfig` and `WorkspaceConfig` are pydantic models, a JSON Schema can be auto-generated and handed directly to an AI as the specification for generating a new config.

---

## Month-Long Implementation Plan

| Week | Focus | Status | Key Deliverables |
|------|-------|--------|-----------------|
| **Week 1** | Interface contracts + async correctness | ✅ **Complete** | `MotionClientProtocol`/`GantryControllerProtocol`, `asyncio.to_thread` wrapping, `PHSensor` decoupled, ghost-thread generation counter, homing state calibration guard |
| **Week 2** | Sensor chain + workspace layer + package split | ✅ **Complete** | `MockPHSensor`, `WorkspaceManager`, `PlateGeometry`, 56 smoke tests, per-device packages (`chem_bench_gantry` / `chem_bench_ph` / `chem_bench_client`), uv workspace |
| **Week 3** | Frontend rebuild + `DeviceInfo` | ✅ **Complete** | Full PySide6 UI: `MainWindow`, `ServerBrowserDialog`, `GantryWidget`, `PHSensorWidget`, `WorkspaceLoader`, dual DARK/LIGHT themes, MDI canvas, plugin device architecture (`core/` + `devices/`), rxnbench namespace rename |
| **Week 4** | AI onboarding scaffold + polish | Pending | JSON manifest schemas, `OnboardingFeature` SiLA service, TLS config guide, fix `install.sh` + `install_service.sh`, end-to-end mock-mode test run |

---

## Dynamic Discovery Architecture

*June 2026 — replaced `_KNOWN_FEATURES` probe loop with `SiLAService.GetImplementedFeatures`.*

### Feature → Descriptor → Frontend Tab pipeline

```
SiLAService.GetImplementedFeatures          (always present — mandatory SiLA2 core feature)
  │  returns list[str] of fully-qualified feature identifiers
  │  e.g. ["org.silastandard/core/SiLAService/v1",
  │         "edu.iastate.ames/rxnbench/Gantry/v0"]
  ▼
core/device_registry.panel_for(server, theme)
  │  calls devices.all_devices() → iterates FEATURE_FRAGMENTS on each plugin
  │  first match wins → calls mod.create_widget(server, theme)
  ▼
QMdiSubWindow added to MDI canvas
  └─ GantryWidget / PHSensorWidget / GenericDeviceWidget
```

### What changed

| Before | After |
|--------|-------|
| `_KNOWN_FEATURES: list[dict]` — hardcoded pkg/svc/probe for each feature | `devices/<name>/__init__.py` — `FEATURE_FRAGMENTS` + `create_widget()` per plugin |
| `_probe_feature(pkg, svc, method)` — one gRPC call per known feature | `SiLAService.GetImplementedFeatures` — one call; fragments matched against result |
| `if "Motion Platform" in found:` stream start branch | Plugin `create_widget()` constructs and returns the correct `QWidget` |
| Adding a device required editing `_FEATURE_REGISTRY` + multiple handler dicts | Drop a new `devices/<name>/` folder — zero core edits |

---

## Remaining Hardcoded Components

| Component | Location | Notes |
|-----------|----------|-------|
| `_PKG`, `_SVC` constants | `sila_client.py` | Required for stream/command method paths — correct to keep. |
| `GantryWidget`, `PHSensorWidget` layouts | `devices/gantry/widget.py`, `devices/ph_sensor/widget.py` | Hand-authored per device. `GenericDeviceWidget` provides a fallback for unknown servers. |
| Motion Platform proto stubs | `proto/motion_platform_pb2.py` | One proto per feature; new features need their own proto + compiled stub. |
| ~~`X_MAX, Y_MAX, Z_MAX`~~ | ~~`sila_client.py`~~ | **REMOVED** — replaced by `GetLimits` SiLA command + `limits_updated` signal. |
| ~~`if "Motion Platform" in found:` stream start~~ | ~~`sila_client.py`~~ | **REMOVED** — `FeatureDescriptor.start_streams(client, gen)` callback. |

---

## Path Toward Metadata-Driven UI

### Layer 1: Feature-scoped stream/command registry *(IMPLEMENTED)*

`FeatureDescriptor` carries a `start_streams` callback. Tab injection/removal handled via `_tab_inject_handlers` / `_tab_remove_handlers` dicts in `MainWindow`. Adding a second feature requires one new `FeatureDescriptor` plus one handler dict entry. No `if` branches to touch.

### Layer 2: FDL-driven widget generation

`SiLAService.GetFeatureDefinition(identifier)` returns FDL XML describing all commands, properties, and data types for any implemented feature. A UI generator could read this and produce a generic "commands + properties" tab without a hand-authored tab builder:

```
GetFeatureDefinition(identifier)
  │  returns FDL XML
  ▼
Parse FDL → list of commands, properties, data types
  ▼
GenericFeatureTab: auto-generated QWidget with one button per command,
                   one display row per observable property
```

The `GetFeatureDefinition` call already works — only the FDL parser and widget generator are missing.

---

## Path Toward AI-Assisted Device Onboarding

### Minimal AI onboarding loop (near-term)

Given a new instrument (e.g. a conductivity probe):

1. **AI generates a new backend package** — follows `chem_bench_ph` as the template. Writes `feature.py`, `interfaces.py`, `server.py`, `_cli.py`. CDK patterns (`@sila.ObservableProperty`, `@sila.UnobservableCommand`) are explicit enough for an AI to follow from existing examples.

2. **AI generates the YAML toolhead/config** — the schema in `toolhead_config_template.yaml` provides the contract. An AI can fill it from a datasheet.

3. **AI creates a `devices/<name>/` plugin** — `__init__.py` with `FEATURE_FRAGMENTS` + `create_widget()`, plus a `QWidget` subclass. No core files need editing; `device_registry.py` discovers it automatically.

4. **AI adds one workspace member** — `pyproject.toml` `[tool.uv.workspace] members` gains the new package dir.

5. **Server restart** — `GetImplementedFeatures` returns the new identifier. Frontend picks it up on next connect.

### Gap: no `OnboardingFeature` API

Steps 1–4 still require code changes. A future `OnboardingFeature` SiLA service (Phase 6) would accept a JSON device description, validate it, write the config, and hot-reload the feature registry.

### Gap: no pydantic validation on configs

AI-generated `ToolheadConfig` YAMLs cannot be automatically validated before use. A wrong field name fails silently. Migrating to pydantic models produces a JSON Schema an AI can treat as the exact contract.

---

## Architecture Stabilization Pass

*June 2026 — four-phase hardening of the SiLA2 + PySide6 stack.*

### Phase 1 — Critical Runtime Fixes

**1a. Blocking I/O in async SiLA handlers — FIXED**
All `Gantry` command and property handlers use `await asyncio.to_thread(...)` for every call reaching `MoonrakerClient`. In-memory reads (`ToolheadManager`, `HomingManager`) intentionally NOT wrapped.

**1b. Ghost stream threads on rapid reconnect — FIXED**
`SilaClient` maintains `self._gen: int`. Every `connect_to()` increments `_gen`. Threads exit the moment `self._gen != my_gen`.

**1c. Unsafe homing state persistence — FIXED**
`HomingManager._is_calibrated` is `True` only after `home_auto()` or `finish_homing()`. `save()` raises `RuntimeError` if `_is_calibrated` is `False`.

### Phase 2 — Architectural Cleanups

**Feature dispatch callbacks — FIXED**
`FeatureDescriptor` carries `start_streams(client, gen)`. No `if "Motion Platform"` branches anywhere.

### Phase 3 — Discovery + Config Hardening

**GetLimits command — ADDED**
Backend: `GantryControllerProtocol.get_limits() -> str` returns `"x_min|x_max|y_min|y_max|z_min|z_max"`. SiLA feature exposes `@sila.UnobservableCommand`. Frontend: `limits_updated(x_min, x_max, y_min, y_max, z_min, z_max)` signal; `PositionGrid` and `ZBar` updated accordingly.

### Phase 4 — Test + Safety Layer

56 smoke tests in `software/backend/gantry/tests/`:

| File | Tests | Coverage |
|------|-------|----------|
| `test_motion_controller.py` | 8 | `get_limits`, `move_to` (in-bounds + 3 limit violations), `jog`, save guard, save-after-homing |
| `test_toolhead_manager.py` | 7 | YAML discovery, geometry load, clear, mount state, `sensor_type` exposed/cleared, unknown toolhead |
| `test_well_plate.py` | 20 | 96-well + 24-well: `PlateGeometry` label parsing, coordinate math, `list_available()`, `load()`, out-of-range errors |
| `test_workspace_manager.py` | 13 | `load_from_yaml`, `resolve_well`, standard/rotated_90 orientation, short label, unknown plate, clear |
| `test_feature_discovery.py` | 8 | Exact match, case-insensitive, mixed-case, unknown ignored, empty list, multi-feature, registry uniqueness |

Run with: `make test-gantry` (or `PYTHONPATH="" uv run --package chem-bench-gantry pytest gantry/tests/ -v` directly).

`PYTHONPATH=""` is required to strip the ROS2 Jazzy system Python path before pytest plugin discovery.

---

## Decision Record: BaseSensor Simplification

**Date:** June 2026

### Decision

Simplify `BaseSensor`. Remove `@command`/`@observable` decorators and `manifest()`. Keep `SensorReading`, `sensor_id`, `display_name`, `description`, and `read()` as abstract.

### Reasoning

`BaseSensor.manifest()` was designed as a runtime capability metadata layer. The CDK already owns this responsibility at a more useful layer. The CDK's `@sila.ObservableProperty`, `@sila.UnobservableCommand`, and FDL generation produce machine-readable feature descriptions at the SiLA/gRPC protocol layer — the layer that clients actually consume. The `@command`/`@observable` decorators were a parallel annotation system to the CDK, operating at the wrong layer and never consumed by anything.

### Migration Notes

- `chem_bench_ph/base_sensor.py`: removed `import inspect`, `command()`, `observable()`, `manifest()`, `calibrate()` abstract, `status()` abstract.
- `chem_bench_ph/atlas_ph_sensor.py`: removed decorator usages. Method implementations unchanged.
- `chem_bench_ph/interfaces.py`: unchanged — still imports `SensorReading` from `base_sensor`.
- `chem_bench_ph/feature.py`: unchanged — depends on `PHSensorProtocol`, not `BaseSensor`.

---

## MotionPlatformController Subsystem Refactor

*June 2026 — single-class motion controller split into three focused subsystems.*

### New Dependency Graph

```
GantryController  (orchestrator — owns cross-subsystem calculations only)
  │
  ├── ToolheadManager ─────────────────────────────────→ ToolheadConfig / ToolheadGeometry
  │     (hardware agnostic, no client import)                  └─ toolheads/*/yaml
  │
  ├── HomingManager ───────────────────────────────────→ MotionClientProtocol
  │     (independent of toolhead logic)                        └─ homing_state.py
  │                                                                 └─ ~/.chem_bench/homing_state.json
  └── MotionEngine ────────────────────────────────────→ MotionClientProtocol (only import)
        (safe clearance travel sequence only)
```

**Coupling rule enforced in each subsystem:**

| Subsystem | Imports from motion layer | Imports toolhead? | Imports homing? |
|-----------|--------------------------|-------------------|-----------------|
| `ToolheadManager` | None | — | No |
| `HomingManager` | `MotionClientProtocol` | No | — |
| `MotionEngine` | `MotionClientProtocol` only | No | No |
| `GantryController` | All three subsystems | Yes (reads geometry) | Yes (reads limits) |

**What the controller is now:** a coordinator that reads two subsystems (HomingManager for limits, ToolheadManager for geometry), performs the two derived calculations that span both (`_safe_clearance_z`, `_check_bounds`, and offset compensation in `move_to`), and delegates everything else. It contains no state of its own.

---

## Future Scaling Assessment

*Assessed after proto codegen migration and package restructure, June 2026.*

### What scales well

**Adding a new device**
Follow the `chem_bench_ph` package template. Create a new directory under `software/backend/`, add it to the uv workspace, define a SiLA feature, write a `server.py` and `_cli.py`. The gantry and existing pH packages are untouched. On the frontend, drop a new `devices/<name>/` package with `FEATURE_FRAGMENTS` and `create_widget()` — `device_registry.py` discovers it automatically.

**Adding a new command to `Gantry`**
1. Implement the method in `chem_bench_gantry/feature.py`
2. Add the `rpc` entry to the static section of `gantry/scripts/gen_proto.py`'s `_FOOTER`
3. Run `make gen-proto`
4. Add the wrapper call to `chem_bench_client/client.py`

**Dataclass field additions at the end**
If `Position` or `ToolheadInfo` gain new fields appended at the end, the next `make gen-proto` + recompile produces correct stubs with no change to existing field numbers.

### What doesn't scale

**Field insertion in the middle of a dataclass**
Inserting a field between existing fields in `Position` or `ToolheadInfo` shifts all subsequent field numbers — silent data corruption between server and old frontend stubs. `make check-proto` catches this before it ships.

**The generator is feature-specific**
`gantry/scripts/gen_proto.py` hardcodes `from chem_bench_gantry.feature import Position, ToolheadInfo`. A `PHSensor` or `WellPlate` proto would require either a new generator script or a refactored common generator.

**Observable Command responses are unsubscribed**
`MoveTo` and `Jog` errors mid-move are silently discarded by the frontend. As the experiment layer matures, workflows will need to know whether a move completed successfully — this requires subscribing to the response stream.

**Proto version pinning**
The compiled `_pb2.py` is pinned to `protobuf 6.x`. Major version bumps require `make gen-proto` and coordination between backend dev environment and frontend deployment.
