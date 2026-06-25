# Automated Chem Bench — Architecture Review

**Date:** June 2026  
**Reviewer:** Architectural analysis of commit `e7c34c9`; updated after interface layer migration, proto codegen migration, and Architecture Stabilization Pass  
**Scope:** Full codebase review — all first-party Python source, YAML configs, and tooling

---

## Communication Layer Review

*Added after proto codegen migration (commits `970d2bf` → `41f1c81`, June 2026).*

### What Changed

The 120-line hand-coded varint/LEN codec in `sila_client.py` has been replaced with `grpcio-tools`-generated protobuf stubs. The new pipeline:

```
software/backend/src/chem_bench/features/motion_platform.py
  └── dataclasses.fields(Position)      ← field order: [x, y, z]
  └── dataclasses.fields(ToolheadInfo)  ← field order: [active, name, ..., toolhead_mounted]
          │
          ▼
software/backend/scripts/gen_proto.py   (reads dataclasses only, no CDK internals)
          │  uv run python scripts/gen_proto.py
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

`make check-proto` (added to `software/backend/Makefile`) runs the generator and diffs the output against the committed `.proto`. It fails if they diverge. Run before every commit that changes backend dataclass field order.

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
| `io/interfaces/motion.py` | `MotionClientProtocol`, `MotionControllerProtocol` |
| `io/interfaces/ph_sensor.py` | `PHSensorProtocol` |
| `io/interfaces/camera.py` | `CameraClientProtocol` |

All protocols use `typing.Protocol` (structural typing) and are `@runtime_checkable`.

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
MotionPlatform (SiLA)  →  MotionControllerProtocol  ←  MotionPlatformController
                               MotionClientProtocol  ←  MoonrakerClient
                                                     ←  MockMoonrakerClient
```

Key changes:
- `MotionPlatformController` no longer imports `MoonrakerClient`. The concrete client is
  injected by `__main__.py`, which now owns the wiring decision.
- `moonraker_host` parameter removed from `MotionPlatformController.__init__` — the
  controller no longer knows what Moonraker is.
- `MockMoonrakerClient` divergence is now statically detectable: adding a method to
  `MoonrakerClient` without adding it to `MockMoonrakerClient` will surface as a type
  error against `MotionClientProtocol`.

#### pH stack (before → after)

**Before:**
```
PHSensor (SiLA)  →  AtlasPHSensor (concrete Atlas-specific class)
```

**After:**
```
PHSensor (SiLA)  →  PHSensorProtocol  ←  AtlasPHSensor
```

Key change: `PHSensor.__init__` now accepts any object with `read()`, `calibrate()`,
and `slope()`. A future pH probe (different chip, USB bridge, networked sensor) can be
wired in without touching the feature.

#### Camera stack (before → after)

**Before:**
```
CrowsnestClient — no interface, only __init__ stub
```

**After:**
```
CameraClientProtocol  ←  CrowsnestClient (get_snapshot, get_stream_url stubs)
```

`CrowsnestClient` now has a committed method surface. A future camera SiLA feature
can be written against `CameraClientProtocol` before any HTTP implementation exists.

### Remaining Coupling

| Item | Location | Notes |
|------|----------|-------|
| `CalibrationPoint` enum is pH-specific but lives in `io/interfaces/enums.py` | `io/interfaces/enums.py` | Low priority; will grow into a problem only if other devices also need calibration enums. Move to `io/interfaces/ph_sensor.py` when convenient. |
| ~~Frontend hardcodes `X_MAX, Y_MAX, Z_MAX = 350, 350, 340`~~ | ~~`sila_client.py`~~ | **FIXED** — `GetLimits` SiLA command added; limits fetched at connect time and broadcast via `limits_updated` signal. |
| `MotionPlatformController` still returns concrete `ToolheadGeometry` dataclass | `io/interfaces/motion.py:get_toolhead` | Acceptable — `ToolheadGeometry` is a pure data class (no I/O, no side effects), not a hardware driver. |
| No mock `I2C` bus — `PHSensor` still cannot run in mock mode | `__main__.py:47-49` | Needs a `MockI2CBus` before the sensor chain can be exercised without hardware. Phase 2 item. |
| `CrowsnestClient.get_snapshot` raises `NotImplementedError` | `io/camera/camera_crowsnest_client.py` | HTTP implementation is a Phase 2 item. |

### Future Instrument Integration Assessment

Adding a new instrument now requires the following steps:

**New pH probe (different chip):**
1. Implement a driver (subclass `AbstractI2CDriver` or write from scratch).
2. Implement a sensor class satisfying `PHSensorProtocol` — three methods.
3. Pass it to `PHSensor(sensor=...)` in `__main__.py`. Feature code unchanged.

**New motion platform (different gantry/CNC):**
1. Implement a client satisfying `MotionClientProtocol` — nine methods.
2. Implement a controller satisfying `MotionControllerProtocol` — ~25 methods.
3. Pass the controller to `MotionPlatform(controller=...)`. Feature code unchanged.

**New camera:**
1. Implement a client satisfying `CameraClientProtocol` — two methods.
2. Pass it to a camera SiLA feature when written. Feature code will be interface-clean from day one.

The interfaces make the extension cost explicit and bounded. Before this change, adding a
new pH probe required editing a SiLA feature. After, it requires only satisfying a
three-method Protocol.

---

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
Operator Machine (Linux/Mac/Win)          Raspberry Pi                   Sovol SV08
──────────────────────────────────        ─────────────────              ─────────────────
chem_bench_ui (PySide6 + gRPC)            chem_bench (SiLA2 server)      H616 ARM (Linux)
  SilaClient                              Gantry feature ──────────────> Moonraker :7125
  ├─ raw gRPC :50051                      PHSensor feature                 └─ Klipper
  └─ grpcio-tools generated stubs         GantryController                  └─ MCU (serial)
      (motion_platform_pb2)               MoonrakerClient                    └─ steppers
                                          AtlasPHSensor (mock or real I2C)
                                          homing_state.json (~/.chem_bench/)
                                          machine.yaml (~/.chem_bench/)
```

The backend runs on a Raspberry Pi (or any Linux host) and exposes a SiLA2 gRPC server on port 50051. The frontend runs on the operator's machine and connects to that server. The SV08 runs Moonraker on the onboard H616 SoC; the backend drives it over HTTP.

### Module Map

#### Backend (`software/backend/src/chem_bench/`)

| File | Purpose |
|------|---------|
| `__main__.py` | App factory. Loads `MachineConfig`, discovers Moonraker, wires `GantryController` into `Gantry` feature. Registers `PHSensor` (mock under `CHEM_BENCH_MOCK=1`, real `AtlasPHSensor` on RPi). Camera is an empty stub. |
| `machine_config.py` | `MachineConfig` dataclass. Loads from `~/.chem_bench/machine.yaml`; falls back to built-in defaults. Owns axis limits and `moonraker_fallback_host`. |
| `_cli.py` | `chem-bench` console script. Locates `config.json` and shims into `unitelabs.cdk.cli.connector`. |
| `features/gantry.py` | SiLA2 Gantry feature. ObservableProperties: `position`, `state`, `toolhead_info`, `has_saved_state`. Commands: `move_to`, `jog`, `engage_tool`, `disengage_tool`, homing suite, toolhead management, workspace management (`set_workspace`, `load_workspace_yaml`, `move_to_well`, `list_workspaces`), `save_and_park`, `get_limits`. |
| `features/ph_sensor.py` | SiLA2 feature for pH. Registered in `__main__.py` when a pH sensor is available. |
| `features/camera_feature.py` | Empty docstring stub. |
| `io/base_driver.py` | `AbstractI2CDriver` ABC. Handles send/read/delay pattern over I2C so subclasses only implement `_parse_response`. |
| `io/base_sensor.py` | `BaseSensor` ABC + `SensorReading` dataclass. Enforces `read()`. Sensor identity only — capability metadata is owned by the CDK layer. |
| `io/errors.py` | Domain exceptions: `DeviceNotFoundError`, `DeviceCommunicationError`, `CalibrationError`, `MotionLimitError`. |
| `io/interfaces/enums.py` | `CalibrationPoint` enum (pH-specific; co-location will need revisiting as more devices are added). |
| `io/interfaces/motion.py` | `MotionClientProtocol`, `GantryControllerProtocol`. Structural protocols for hardware injection and mock seams. |
| `io/interfaces/ph_sensor.py` | `PHSensorProtocol`. Three-method interface: `read()`, `calibrate()`, `slope()`. |
| `io/interfaces/camera.py` | `CameraClientProtocol`. Two-method interface: `get_snapshot()`, `get_stream_url()`. |
| `io/gantry/gantry_controller.py` | Thin orchestrator. Owns cross-subsystem logic: toolhead offset compensation, footprint-aware bounds checking, `_safe_clearance_z`. Delegates to `ToolheadManager`, `HomingManager`, `MotionEngine`, `WorkspaceManager`. Satisfies `GantryControllerProtocol`. |
| `io/gantry/toolhead_manager.py` | `ToolheadManager`. Active toolhead config, mount state, and `sensor_type`. Hardware agnostic — loads from YAML. Exposes `sensor_type: str | None` for sensor registry lookup. |
| `io/gantry/homing_manager.py` | `HomingManager`. Axis limits, manual/auto homing state machine, kinematic-reset jog trick, JSON persistence. |
| `io/gantry/motion_engine.py` | `MotionEngine`. Safe clearance travel sequence (raise → XY → lower). Depends only on `MotionClientProtocol`. |
| `io/gantry/workspace_manager.py` | `WorkspaceManager`. Loads `WorkspaceConfig` YAML (by name or raw string). Resolves well labels to world-space XYZ. Applies plate orientation (`standard` / `rotated_90`). No tip-offset logic — `GantryController.move_to()` handles hardware offsets. |
| `io/gantry/moonraker_client.py` | Synchronous HTTP client for Moonraker REST API (port 7125). POST `/printer/gcode/script` blocks until Klipper completes the move. |
| `io/gantry/mock_moonraker.py` | In-memory drop-in for development without hardware. Activated via `CHEM_BENCH_MOCK=1`. |
| `io/gantry/moonraker_discovery.py` | Parallel mDNS (`zeroconf`) + IPv6 link-local scan. Returns first responding host. |
| `io/gantry/homing_state.py` | JSON persistence of calibrated axis limits in `~/.chem_bench/homing_state.json`. |
| `io/labware/plate_geometry.py` | `PlateGeometry` frozen dataclass. Uniform-spacing plate geometry (ANSI/SLAS standard). `well_position(label)` → `(x, y)` in mm from plate corner. `parse_label("A1")` → `(0, 0)`. `load(name)` / `list_available()` from `io/labware/definitions/`. |
| `io/labware/definitions/96_well_standard.yaml` | ANSI/SBS 96-well standard (9 mm pitch, 8×12, 10.67 mm depth). |
| `io/labware/definitions/24_well_standard.yaml` | ANSI/SBS 24-well standard (19.3 mm pitch, 4×6, 17.4 mm depth). |
| `io/workspace/workspace_config.py` | `WorkspaceConfig` frozen dataclass + YAML loader. `PlacedPlate` (id, plate_type, origin XYZ, orientation). `Orientation` enum: `standard` / `rotated_90`. `from_yaml()`, `load(name)`, `list_available()`. |
| `io/workspace/definitions/_workspace_template.yaml` | Template for new workspace definitions (prefixed `_` so `list_available()` skips it). |
| `io/ph/atlas_scientific_driver.py` | `AtlasScientificEZO`: raw EZO I2C command set. No pH logic — just protocol. |
| `io/ph/atlas_ph_sensor.py` | `AtlasPHSensor(BaseSensor)`: pH-specific logic (calibration, slope, temperature compensation). |
| `io/ph/mock_ph_sensor.py` | `MockPHSensor`. Returns fixed pH 7.00, no-op calibration. Used under `CHEM_BENCH_MOCK=1`. |
| `io/toolheads/toolhead_config.py` | `ToolheadConfig` + `ToolheadGeometry` dataclasses. `sensor_type: str | None` lives on `ToolheadConfig` (not `ToolheadGeometry`) — it describes the attached sensor, not physical shape. |
| `io/toolheads/ph_probe/ph_probe_toolhead.yaml` | Real toolhead config: 44×25 mm footprint, 110 mm tip depth, 25 mm engage depth. Declares `sensor_type: ph`. |
| `io/toolheads/toolhead_config_template.yaml` | Template for adding new toolheads. |
| `io/camera/camera_crowsnest_client.py` | 15-line stub. `CrowsnestClient.__init__` only; no HTTP calls. |

#### Frontend (`software/frontend/src/chem_bench_ui/`)

*Mid-rebuild. The previous widget set was deleted; a new UI is being designed. Only the SiLA client layer and two canvas widgets survive.*

| File | Purpose |
|------|---------|
| `app.py` | 21-line stub with `# TODO: build and show main window`. Not functional. |
| `sila_client.py` | gRPC channel management, `grpcio-tools`-generated stub codec, Qt signals for position/state/toolhead/connection, background streaming threads. |
| `themes.py` | `DARK`/`LIGHT` color palettes as dicts. `build_qss(t)` generates a QSS stylesheet string. |
| `proto/motion_platform.proto` | Proto3 source generated by `gen_proto.py`. Committed; regenerate with `make gen-proto`. |
| `proto/motion_platform_pb2.py` | Compiled Python stubs. Committed; regenerate with `make gen-proto`. |
| `proto/sila_service_pb2.py` | Compiled stubs for `SiLAService.GetImplementedFeatures`. |

**Widgets surviving the rebuild (`widgets/`):**

| File / Class | Role |
|--------------|------|
| `position_grid.py` / `PositionGrid` | Custom `QPainter` 2D top-down XY canvas. Shows gantry rails, carriage, toolhead footprint, tip crosshair, click-to-move target. |
| `zbar.py` / `ZBar` | Custom `QPainter` vertical Z indicator. Shows tip depth and engage range markers. |

**Deleted (pending rebuild):** `main_window.py`, `homing_panel.py`, `jog_panel.py`, `server_panel.py`, `toolhead_diagram.py`, `toolhead_panel.py`.

### Communication Layer

| Layer | Transport | Details |
|-------|-----------|---------|
| Frontend → Backend | gRPC (insecure, port 50051) | Raw `grpc.Channel` with `grpcio-tools`-generated stubs (`motion_platform_pb2`). ObservableProperties → `unary_stream`. Commands → `unary_unary`. |
| Backend → SV08 | HTTP REST (port 7125) | `requests.post("/printer/gcode/script")` blocks until Klipper finishes. `requests.get` for position/state queries. |
| SV08 internal | Serial (ttyS3) | H616 → MCU for real-time stepper pulses. Transparent to this codebase. |
| Discovery (Moonraker) | mDNS + IPv6 | `_moonraker._tcp.local.` via zeroconf + fe80:: neighbor probe in parallel. |
| Discovery (SiLA) | Manual | Operator enters hostname in the connection bar. |

### Infrastructure

| Component | Details |
|-----------|---------|
| Backend runtime | Python 3.12, `uv`, systemd service via `scripts/install_service.sh` |
| Backend dependencies | `unitelabs-cdk` (SiLA2), `requests`, `pyyaml`, `zeroconf`; optional `smbus2` for RPi I2C |
| Frontend runtime | Python 3.12, `uv`, started via `chem-bench-ui` console script |
| Frontend dependencies | `PySide6`, `grpcio>=1.60.0`, `protobuf>=6.33.5`, `zeroconf` |
| SiLA CDK version | `unitelabs-cdk==0.11.2`, `unitelabs-sila==0.8.0` |
| Config | `config.json` (SiLA server identity, TLS off, UUID `a9a1052f`) |

---

## Dependency Graph

```
chem_bench_ui.app  (stub — frontend rebuild pending)
  └── SilaClient
        ├── grpc.Channel ──────────────────────────────────→ chem_bench SiLA server :50051
        └── motion_platform_pb2 (grpcio-tools generated)
              └── derives from motion_platform.proto
                    └── generated by gen_proto.py
                          └── dataclasses.fields(Position, ToolheadInfo)

_FEATURE_REGISTRY (display name → identifier mapping)
  └── _fetch_implemented_features() → SiLAService.GetImplementedFeatures

chem_bench.__main__  (app factory)
  ├── MachineConfig.load() ────────────────────────────→ ~/.chem_bench/machine.yaml (or defaults)
  ├── Connector (unitelabs-cdk)
  ├── Gantry feature
  │     └── GantryController  (satisfies GantryControllerProtocol)
  │           ├── ToolheadManager ──────────────────────→ io/toolheads/*/name_toolhead.yaml
  │           │     sensor_type: str | None ────────────→ sensor_registry lookup
  │           ├── HomingManager
  │           │     ├── MotionClientProtocol
  │           │     └── homing_state ─────────────────→ ~/.chem_bench/homing_state.json
  │           ├── MotionEngine
  │           │     └── MotionClientProtocol (move, jog, get_position, get_state)
  │           │           ├── MoonrakerClient ─────────→ SV08 Moonraker :7125
  │           │           │     └── requests.post/get      └─ Klipper → MCU → motors
  │           │           └── MockMoonrakerClient (CHEM_BENCH_MOCK=1)
  │           └── WorkspaceManager
  │                 ├── WorkspaceConfig ──────────────→ io/workspace/definitions/*.yaml
  │                 └── PlateGeometry ────────────────→ io/labware/definitions/*.yaml
  └── PHSensor feature  [registered when sensor available]
        ├── AtlasPHSensor → AtlasScientificEZO → smbus2.SMBus(1)  (real hardware)
        └── MockPHSensor  (CHEM_BENCH_MOCK=1)
```

---

## Architectural Strengths

**1. Clean three-layer I/O stack**
Driver → Sensor → Feature, each with a single responsibility. `AtlasScientificEZO` knows only I2C bytes. `AtlasPHSensor` knows pH chemistry and the `BaseSensor` contract. `PHSensor` knows only SiLA endpoints and delegates everything else. Hardware can be swapped at the driver or sensor layer without touching the SiLA interface.

**2. Config-driven hardware registration**
Toolheads and well plates are YAML files in named subdirectories. Adding a new toolhead requires zero Python changes — drop in a folder matching the schema and it appears in `ListToolheads`. The same pattern is established (but not yet exploited) for well plates.

**3. Structural mock seam**
`MotionPlatformController` accepts any `client` object with the right methods. `MockMoonrakerClient` is a complete in-memory drop-in. Development and CI can run the full SiLA server without physical hardware via `CHEM_BENCH_MOCK=1`.

**4. Session persistence**
Calibrated axis limits survive a clean shutdown via `homing_state.json`. The "Restore from previous session" banner in the UI informs the operator when limits were restored, prompting them to verify position before running experiments.

**5. Dynamic feature tab injection**
`_FEATURE_REGISTRY` + `_on_features_discovered` (dispatching via `_tab_inject_handlers` / `_tab_remove_handlers` dicts) inserts and removes UI tabs based on what the server reports via `SiLAService.GetImplementedFeatures`. The UI is not hardwired to a fixed feature set at compile time.

**6. `BaseSensor` — sensor identity and reading envelope**
`BaseSensor` provides `sensor_id`, `display_name`, `description`, and the `SensorReading` timestamped reading dataclass. Capability metadata (commands, observables, types) is owned by the SiLA CDK layer (`@sila.ObservableProperty`, `@sila.UnobservableCommand`, FDL generation) — the CDK is the correct place for AI-assisted onboarding and UI generation since it operates at the protocol layer that clients actually consume. The `@command`/`@observable` decorators and `manifest()` method that previously lived here were a parallel annotation system to the CDK and have been removed.

**7. Moonraker auto-discovery**
mDNS and IPv6 link-local probes run in parallel via thread executor. The backend finds the SV08 without any IP configuration for both WiFi and direct-cable topologies. Falls back to a static IP if both fail.

**8. Toolhead-aware bounds checking**
`_check_bounds` applies footprint half-widths and tip Z offset, so a wide toolhead can't move to a position where its edge leaves the build envelope. This is enforced in the controller, not left to callers.

**9. Safe clearance travel**
`move_to` always raises Z to `clearance_z` (adjusted for tip length) before XY travel, then lowers to the target Z. This is an invariant in `MotionPlatformController`, not a convention that callers must remember.

**10. Homing state machine with manual mode**
The kinematic pre-reset trick in `jog()` during manual homing (`_HOMING_SAFE_MID`) enables axis limit discovery with a toolhead mounted, working around Klipper's position bounds. The accumulated displacement approach in `confirm_x_max`/`confirm_y_max` tracks real travel without relying on Klipper's reported position (which is meaningless after kinematic resets).

---

## Architectural Weaknesses

**1. ~~`PHSensor` feature is coupled to the concrete implementation class~~ FIXED**
`PHSensor` now accepts `PHSensorProtocol` (`io/interfaces/ph_sensor.py`). Any sensor satisfying `read()`, `calibrate()`, `slope()` can be used without touching the feature.

**2. ~~`MoonrakerClient` has no enforced interface contract~~ FIXED**
`MotionClientProtocol` (`io/interfaces/motion.py`) defines the full nine-method surface. `MoonrakerClient` and `MockMoonrakerClient` both satisfy it structurally. Divergence is now statically detectable.

**3. ~~Blocking synchronous I/O in async SiLA handlers~~ FIXED**
All `MotionPlatform` handlers now use `await asyncio.to_thread(...)` for every call reaching `MoonrakerClient`. In-memory reads (`ToolheadManager`, `HomingManager`) intentionally unwrapped to avoid thread-pool overhead on high-frequency observables.

**4. ~~Frontend is a 2000-line monolith~~ FIXED**
`app.py` has been split into focused modules: `sila_client.py`, `main_window.py`, `themes.py`, and `widgets/` (seven widget files). See Phase 4 migration notes.

**5. ~~Hand-coded protobuf in the frontend~~ FIXED**
`sila_client.py` now uses `grpcio-tools`-generated stubs (`motion_platform_pb2.py`). Field numbers are derived from `dataclasses.fields()` in `gen_proto.py`, matching the CDK runtime. Drift is detected by `make check-proto`. See Communication Layer Review above.

**6. Well plates are not connected to anything**
`WellPlate` (`labware/well_plate.py`) is complete with coordinate model, label parsing, and well iteration, but has no SiLA feature, no workflow, and no UI. A motion command currently requires raw XYZ coordinates. The system cannot express "move to well A3 of plate P." Phase 3 adds the SiLA `WellPlate` feature.

**7. `CalibrationPoint` enum lives in `interfaces/enums.py` but is pH-specific**
As more devices are added, this shared file risks becoming a dumping ground for unrelated enums. Device-specific enums should live co-located with their device modules.

**8. ~~Frontend hardcodes machine axis limits~~ FIXED**
`X_MAX, Y_MAX, Z_MAX` constants removed from `sila_client.py`. The `GetLimits` SiLA command is fetched at connect time; `limits_updated(x_min, x_max, y_min, y_max, z_min, z_max)` signal propagates the values to `PositionGrid` and `ZBar`.

**9. I2C bus is never instantiated**
The path from the Raspberry Pi's I2C bus to `AtlasPHSensor` is fully designed but the `smbus2.SMBus(1)` call that would wire it up is absent from `__main__.py`. There is no mock I2C bus for development either.

**10. ~~Frontend accesses a private attribute~~ FIXED**
`MainWindow` now uses `self._client.host` (public property). `SilaClient._host` is no longer accessed externally.

**11. ~~No test coverage~~ FIXED**
37 smoke tests added in `software/backend/tests/`. Covers `MotionPlatformController` (mock client), `ToolheadManager` YAML loading, `WellPlate` coordinate math, and `FeatureDescriptor` registry matching. Run with `make test`.

**12. No TLS in the production config**
`config.json` has `"tls": false`. Acceptable for isolated development, but requires a plan before lab deployment.

---

## Technical Debt

| Item | Location | Severity |
|------|----------|----------|
| pH probe `tip_x`/`tip_y` not yet measured — zeros used | `io/toolheads/ph_probe/ph_probe_toolhead.yaml` | Low |
| `camera_feature.py` is an empty docstring — no implementation | `features/camera_feature.py` | Low |
| `CrowsnestClient` is a stub with no HTTP logic | `io/camera/camera_crowsnest_client.py` | Low |
| `CalibrationPoint` enum is pH-specific but lives in shared `io/interfaces/enums.py` | `io/interfaces/enums.py` | Low |
| Frontend `app.py` is a non-functional stub — `MainWindow` and all widget panels were deleted and not yet replaced | `frontend/src/chem_bench_ui/app.py` | **High** — UI cannot run |
| No workspace or labware UI on frontend — `WorkspaceManager` / `PlateGeometry` are backend-only | — | Medium |
| Proto stubs committed as generated code; `make check-proto` guards drift in CI | `proto/motion_platform_pb2.py` | Low |
| ~~PHSensor feature not registered, no mock pH sensor~~ **FIXED** — `MockPHSensor` added; `__main__.py` registers `PHSensor` in both mock and real paths | — | Resolved |
| ~~Machine axis limits hardcoded in `__main__.py`~~ **FIXED** — `MachineConfig` loads from `~/.chem_bench/machine.yaml` with defaults | — | Resolved |
| ~~`sensor_type` on `ToolheadGeometry` (wrong layer)~~ **FIXED** — moved to `ToolheadConfig`; `ToolheadManager.sensor_type` property exposed | — | Resolved |
| ~~`WorkspaceManager.load_from_yaml` used unnecessary `StringIO`~~ **FIXED** | — | Resolved |
| ~~`GantryControllerProtocol` missing `load_workspace_from_yaml`~~ **FIXED** | — | Resolved |

---

## Risks

| Risk | Location | Impact | Likelihood |
|------|----------|--------|------------|
| Proto version skew — `motion_platform_pb2.py` was compiled with `grpcio-tools==1.81.1` / `protobuf==6.33.6`. Upgrading grpcio-tools without regenerating stubs can cause import-time `ValidateProtobufRuntimeVersion` failures | `proto/motion_platform_pb2.py` | **Low** — caught at import not at runtime | Rare |
| Observable Command response streams not consumed — `MoveTo` and `Jog` errors mid-move are silently discarded by the frontend | `sila_client.py` | **Low** — frontend only sees gRPC status errors, not structured progress/completion | Low |
| No TLS — bare gRPC on any network the Pi is on | `config.json` | **Low** in isolated lab network, **High** if shared | Context-dependent |
| ~~Blocking `requests.post()` in `async def` SiLA handlers~~ **FIXED** — all handlers use `await asyncio.to_thread(...)` | — | Resolved | — |
| ~~Homing state saved with default (uncalibrated) limits~~ **FIXED** — `_is_calibrated` guard in `HomingManager.save()` | — | Resolved | — |
| ~~Ghost threads on rapid reconnect~~ **FIXED** — generation counter `self._gen` in `SilaClient` | — | Resolved | — |
| ~~`MockMoonrakerClient` can silently diverge from `MoonrakerClient`~~ **FIXED** — `MotionClientProtocol` enforces the shared surface | — | Resolved | — |
| ~~PHSensor feature imports `AtlasPHSensor` directly~~ **FIXED** — feature now accepts `PHSensorProtocol` | — | Resolved | — |
| ~~Hand-coded protobuf field numbers can silently mismatch CDK wire format~~ **FIXED** — stubs generated from same `dataclasses.fields()` source; drift caught by `make check-proto` | — | Resolved | — |

---

## Recommended Migration Order

### Phase 1 — Interface contracts and async correctness (Week 1)

These are the highest-risk items. Fix them before adding new features.

1. ✅ **Define `MotionClientProtocol` and `MotionControllerProtocol`** — done. Both live in `io/interfaces/motion.py`. `motion_platform_controller.py` now depends on `MotionClientProtocol`; `features/motion_platform.py` depends on `MotionControllerProtocol`.

2. ✅ **Fix blocking I/O** — done. All `MoonrakerClient` calls wrapped in `await asyncio.to_thread(...)` at the SiLA feature layer.

3. ✅ **Decouple `PHSensor` from concrete class** — done. `PHSensor.__init__` now accepts `PHSensorProtocol` (`io/interfaces/ph_sensor.py`). Atlas-specific pH-only methods (`slope`) are included in the protocol.

4. ✅ **Expose `SilaClient.host` as a public property** — done. `MainWindow` uses `self._client.host`; `SilaClient._host` is no longer accessed externally.

### Phase 2 — Complete the sensor chain (Week 1-2)

5. **Wire up `AtlasPHSensor` in `__main__.py`** — add smbus2 bus instantiation (or a mock I2C bus under `CHEM_BENCH_MOCK=1`) and register `PHSensor` feature. This is the path to any chemistry measurement.

6. **Add mock I2C bus** — a `MockI2CBus` alongside `MockMoonrakerClient` so the full feature set (motion + pH) works in mock mode without any hardware.

7. **Implement basic `CrowsnestClient`** — MJPEG snapshot via `requests.get`. Register a minimal camera SiLA feature.

### Phase 3 — Well plate workflow layer (Week 2)

8. **Add `WellPlate` SiLA feature** — exposes `ListPlates`, `SetPlate(name)`, `MoveTo(label)`. Uses `WellPlate.well_position_by_label()` to translate well addresses to XYZ, then delegates to `MotionPlatformController.move_to()`.

9. **Expose plate overlay in the frontend** — when a plate is set, draw the plate footprint and well grid on `PositionGrid`. Click-to-move snaps to the nearest well center.

10. ✅ **Read axis limits from the server** — done. `GetLimits` SiLA command added end-to-end. Hardcoded `X_MAX, Y_MAX, Z_MAX` constants removed from `sila_client.py`.

### Phase 4 — Frontend decomposition (Week 2-3)

11. ✅ **Split `app.py`** — done. Modules: `sila_client.py`, `main_window.py`, `themes.py`, `widgets/` (seven files). Proto codec replaced with generated stubs (`motion_platform_pb2`). See Communication Layer Review above.

12. ✅ **Add pytest scaffold** — done. 37 smoke tests in `software/backend/tests/`. Run with `make test` (uses `PYTHONPATH=""` to isolate from ROS2 system plugins).

### Phase 5 — Metadata-driven UI foundation (Week 3)

13. **Add `DeviceInfo` SiLA feature** — returns structured JSON describing all registered features, sensor manifests, toolhead list, and plate list.

14. ✅ **Migrate feature discovery to server-sourced** — `SiLAService.GetImplementedFeatures` replaces the `_KNOWN_FEATURES` probe loop. `_FEATURE_REGISTRY` maps identifiers to display names. `_probe_feature` removed.

15. **Migrate configs to `pydantic` models** — replace plain dataclasses in `ToolheadConfig` and `WellPlate` with `pydantic.BaseModel`. This adds schema validation, JSON serialization, and makes AI-generated configs verifiable.

### Phase 6 — AI onboarding scaffold (Week 4)

16. **Define JSON manifest schema** — a versioned JSON Schema for each device type (toolhead, sensor, plate, instrument). The schema is the contract an AI must satisfy to onboard a new device.

17. **Add `OnboardingFeature` SiLA service** — accepts a JSON device description, validates it against the schema, writes the config file, and hot-reloads the feature registry.

18. **TLS config guide** — document the cert generation and `config.json` changes needed for lab deployment.

---

## Capability-Based Architecture Assessment

The system is at an early stage of capability-based design.

| Principle | Status | Gap |
|-----------|--------|-----|
| Toolheads declare physical geometry | ✅ YAML configs, YAML-driven | Geometry only; no electrical/protocol capability declared |
| Sensors self-describe via CDK decorators | ✅ CDK handles this at the SiLA layer | FDL/feature introspection not yet consumed by the frontend |
| UI adapts to discovered features | ✅ `_on_features_discovered` inserts tabs | Server-driven via `SiLAService.GetImplementedFeatures`; tab content still hand-authored |
| New instruments require minimal code | ⚠️ Backend: YAML drop-in | Frontend: requires new widget + one `FeatureDescriptor` in `_FEATURE_REGISTRY` |
| Workflows depend on capabilities, not hardware | ❌ Not yet | No workflow layer; SiLA commands are raw hardware operations |
| Runtime capability registry | ❌ Not yet | Devices enumerated at startup in `__main__.py`; no runtime negotiation |

The architecture is **capability-oriented at the configuration level** (YAML files, manifest decorators) but not yet at the **runtime level** (no registry, no negotiation, no capability query endpoint).

The path from here to a full capability-based system is Phase 5 (`DeviceInfo` feature) and Phase 6 (`OnboardingFeature`). The CDK's FDL generation is the correct foundation for capability metadata — it operates at the protocol layer clients actually consume, making it the right input for AI-assisted onboarding and metadata-driven UI generation.

---

## AI-Assisted Device Onboarding Assessment

### Existing foundations (strong)

- The CDK's FDL generation (`@sila.ObservableProperty`, `@sila.UnobservableCommand`, etc.) produces the machine-readable feature description at the protocol layer. This is the correct metadata target for AI-assisted onboarding — it describes what clients see, not internal implementation details.
- YAML-driven `ToolheadConfig` and `WellPlateConfig` are easy for an AI to generate from datasheet measurements. The templates provide the schema.
- The Driver → Sensor → Feature separation means an AI can target the correct abstraction level when writing code for a new device.
- The mock infrastructure means an AI-generated driver can be tested in software before hardware is connected.

### Gaps to close

1. **No pydantic validation** — AI-generated YAML configs cannot be automatically validated before use. A wrong field name fails silently (YAML loads the key, dataclass ignores extra keys or raises on missing ones). Pydantic models would catch this at load time with a clear error.

2. **No runtime schema access** — The SiLA FDL (Feature Definition Language) XML is not accessible at runtime. An AI cannot programmatically introspect what parameters a SiLA command accepts. Parameter types and valid ranges exist only in Python source.

3. **No device registry endpoint** — Currently requires a developer to write Python, drop in a YAML, and restart the server. There is no API call that says "register this new device." Phase 6's `OnboardingFeature` fills this gap.

4. **No structured parameter schemas on SiLA commands** — Units, valid ranges, and semantic constraints (e.g. "z must be positive") are enforced in Python logic but not declared in a machine-readable way. An AI generating a workflow cannot know valid parameter ranges without reading the source.

### Recommended path

The most impactful next step for AI onboarding is **pydantic models for configs** (Phase 5). Once `ToolheadConfig` and `WellPlateConfig` are pydantic models, a JSON Schema can be auto-generated from them and handed directly to an AI as the specification for generating a new config. This requires no architectural change to the runtime system.

---

## Month-Long Implementation Plan

| Week | Focus | Status | Key Deliverables |
|------|-------|--------|-----------------|
| **Week 1** | Interface contracts + async correctness | ✅ **Complete** | `MotionClientProtocol`/`GantryControllerProtocol`, `asyncio.to_thread` wrapping, `PHSensor` decoupled, `SilaClient.host` property, ghost-thread generation counter, homing state calibration guard |
| **Week 2** | Sensor chain + workspace layer | ✅ **Complete** | `MockPHSensor` + `PHSensor` registered in `__main__.py`, `MachineConfig` externalises axis limits, `WorkspaceManager` + `PlateGeometry`, `load_workspace_yaml` SiLA command, 56 smoke tests |
| **Week 3** | Frontend rebuild + `DeviceInfo` | **In progress** | `sila_client.py` / `themes.py` / `PositionGrid` / `ZBar` survive; `MainWindow` + panels pending rebuild; `DeviceInfo` SiLA feature pending; pydantic configs pending |
| **Week 4** | AI onboarding scaffold + polish | Pending | JSON manifest schemas, `OnboardingFeature` SiLA service, TLS config guide, end-to-end mock-mode test run |

---

*Generated from a full read of the codebase at commit `e7c34c9`. Updated after interface layer migration, proto codegen migration, and Architecture Stabilization Pass (June 2026).*

---

## Decision Record: BaseSensor Simplification

**Date:** June 2026

### Decision

Simplify `BaseSensor`. Remove `@command`/`@observable` decorators and `manifest()`. Keep `SensorReading`, `sensor_id`, `display_name`, `description`, and `read()` as abstract.

### Reasoning

`BaseSensor.manifest()` was designed as a runtime capability metadata layer — sensors would self-describe their commands and observables so UIs and AI tooling could consume the manifest without reading source code. This was architecturally sound in the abstract, but the UnitelabsCDK already owns this responsibility at a more useful layer.

The CDK's `@sila.ObservableProperty`, `@sila.UnobservableCommand`, and FDL generation produce machine-readable feature descriptions at the SiLA/gRPC protocol layer — the layer that clients actually consume. An AI generating a new SiLA feature writes against CDK patterns, not `BaseSensor` patterns. An AI-generated UI reads from CDK-exposed feature metadata, not from `manifest()`. The `@command`/`@observable` decorators were a parallel annotation system to the CDK, operating at the wrong layer and never consumed by anything.

### Future Architecture Impact

- AI-assisted onboarding targets CDK decorator patterns (`sila.Feature` subclass, `@sila.UnobservableCommand`, `@sila.ObservableProperty`) — not `BaseSensor`.
- Metadata-driven UI generation reads CDK FDL output — not `manifest()`.
- `BaseSensor` remains the correct base for sensor identity and the `SensorReading` envelope.
- Future sensors (temperature, ORP, conductivity) inherit `BaseSensor` and must implement `read()`. Device-specific capabilities (`calibrate`, `status`) are implemented on the subclass and exposed through the CDK feature layer.

### Migration Notes

- `io/base_sensor.py`: removed `import inspect`, `command()`, `observable()`, `manifest()`, `calibrate()` abstract, `status()` abstract.
- `io/ph/atlas_ph_sensor.py`: removed `command, observable` imports and all decorator usages. Method implementations unchanged.
- `io/interfaces/ph_sensor.py`: unchanged — still imports `SensorReading` from `base_sensor`.
- `features/ph_sensor.py`: unchanged — depends on `PHSensorProtocol`, not `BaseSensor`.

---

## Remaining Risks

*Updated after Architecture Stabilization Pass, June 2026.*

### Low

**Proto stub / runtime version skew**
`motion_platform_pb2.py` was compiled with `grpcio-tools==1.81.1` (protobuf runtime `6.33.6`). The generated stub calls `_runtime_version.ValidateProtobufRuntimeVersion(Domain.PUBLIC, 6, 33, 5, ...)` at import time. If the frontend environment installs `protobuf<6.x` or `protobuf>=7.x`, the import fails with a clear error rather than silently misencoding. This is a deployment risk, not a correctness risk — it is loud and caught early.

**Observable Command response streams not consumed**
`Jog` and `MoveTo` are `@sila.ObservableCommand()`. The frontend initiates them with `unary_unary` and ignores the server's response stream entirely (progress, completion, errors). A move that fails mid-execution (limit error, emergency stop) will emit an error on the unread stream, but the frontend only sees it if the gRPC status code is non-OK on the initiate call. Structured error responses from observable commands are silently discarded.

**No TLS**
`config.json` has `"tls": false`. Acceptable for an isolated bench-side Ethernet connection. Unacceptable if the RPi is on a shared network or accessed over WiFi.

**~~Blocking synchronous I/O in async SiLA handlers~~ FIXED**
All `MotionPlatform` command and observable property handlers now use `await asyncio.to_thread(...)` for every call that reaches `MoonrakerClient`. See Architecture Stabilization Pass.

**~~Ghost streaming threads on rapid reconnect~~ FIXED**
Generation counter (`self._gen`) in `SilaClient`. Each thread captures its `gen` at start and exits the moment `self._gen != gen`. Only ONE active set of stream threads per connection generation is now guaranteed.

**~~Homing state saved with unverified axis limits~~ FIXED**
`HomingManager._is_calibrated` tracks whether limits were freshly calibrated in this session. `save()` raises `RuntimeError` if `_is_calibrated` is `False` (default after restore-from-disk). `is_calibrated` and `timestamp` are now persisted in the JSON for auditing.

**~~`_client._host` private access~~ FIXED**
`MainWindow` now uses `self._client.host` (public property on `SilaClient`).

**~~Frontend hardcodes machine axis limits~~ FIXED**
`X_MAX, Y_MAX, Z_MAX` constants removed from `sila_client.py`. Limits are now fetched via the `GetLimits` SiLA command at connection time and propagated via the `limits_updated` signal.

---

## Future Scaling Assessment

*Assessed after proto codegen migration, June 2026.*

### What scales well

**Adding a new command to `MotionPlatform`**
Adding a new `@sila.UnobservableCommand()` with no parameters requires only:
1. Implement the method in `motion_platform.py`
2. Add `rpc NewCommand (Empty) returns (Empty);` to the static section of `gen_proto.py`'s `_FOOTER`
3. Run `make gen-proto`
4. Add `def new_command(self): self._fire("NewCommand")` to `sila_client.py`

Adding a command with parameters requires also adding a `message NewCommand_Parameters {...}` entry. The generator will assign correct field numbers if the parameters come from a dataclass, or they can be added to the static template for function-signature-based parameters.

**Dataclass field additions at the end**
If `Position` or `ToolheadInfo` gain new fields appended at the end (not inserted in the middle), the next `make gen-proto` + recompile produces correct stubs with no change to existing field numbers. The CDK and frontend both handle unknown trailing fields gracefully.

**Multiple features**
The current generator is `MotionPlatform`-specific. The pattern generalises cleanly: a single `gen_proto.py` could iterate over all features in the `features/` package, discover their dataclass return types and function signatures, and emit one `.proto` per feature (or a combined `.proto` with package namespacing). The CDK field-number rule (`dataclasses.fields()` order) applies uniformly to all features.

### What doesn't scale

**Field insertion in the middle of a dataclass**
Inserting a field between existing fields in `Position` or `ToolheadInfo` shifts all subsequent field numbers. The server CDK and frontend stubs would encode/decode the same field numbers at different positions, producing silent data corruption. `make check-proto` catches this before a commit reaches CI, but the fix requires regenerating stubs AND being aware that any frontend version compiled against the old stubs will mis-decode until updated. There is no wire-level backwards compatibility for field insertions.

**The generator is currently feature-specific**
`gen_proto.py` hardcodes `from chem_bench.features.motion_platform import Position, ToolheadInfo` and has static templates for `MotionPlatform`-specific messages. Adding `PHSensor` or a `WellPlate` feature will require either a new generator script per feature or a refactored common generator that introspects the CDK feature class generically.

**Observable Command responses are unsubscribed**
When `MoveTo` or `Jog` fail mid-move (e.g. limit error), the observable command's response stream carries a structured error that the frontend currently ignores. As the experiment layer matures (Phase 3+), workflows will need to know whether a move completed successfully before dispensing reagents. This requires subscribing to the response stream, which means new `Subscribe_MoveTo_Responses` proto messages, a new gRPC stream thread, and a new Qt signal for move completion / error.

**~~Frontend `_KNOWN_FEATURES` is static~~ PARTIALLY RESOLVED**
Discovery is now server-driven via `SiLAService.GetImplementedFeatures`. Adding a second feature (`PHSensor`, `WellPlateFeature`) still requires: one `FeatureDescriptor` in `_FEATURE_REGISTRY`, a new proto file + compiled stub, and a new tab widget. The discovery step no longer requires code changes — only the display mapping and tab builder do.

**Proto version pinning**
The compiled `_pb2.py` is pinned to `protobuf 6.x`. When the `protobuf` library releases a new major version, the stubs must be regenerated. This is a one-command operation (`make gen-proto`) but requires coordination between backend dev environment (which has grpcio-tools) and frontend deployment (which just needs the `protobuf` runtime). Document this in the deployment guide before lab handoff.

---

## MotionPlatformController Subsystem Refactor

*June 2026 — single-class motion controller split into three focused subsystems.*

### New Dependency Graph

```
MotionPlatformController  (orchestrator — owns cross-subsystem calculations only)
  │
  ├── ToolheadManager ─────────────────────────────────→ ToolheadConfig / ToolheadGeometry
  │     (hardware agnostic, no client import)                  └─ io/toolheads/*/yaml
  │
  ├── HomingManager ───────────────────────────────────→ MotionClientProtocol
  │     (independent of toolhead logic)                        (set_kinematic_position,
  │                                            ┌───────────────  home, move, get_homed_axes)
  │                                            └─────────────→ homing_state.py
  │                                                               └─ ~/.chem_bench/homing_state.json
  └── MotionEngine ────────────────────────────────────→ MotionClientProtocol (only import)
        (safe clearance travel sequence only)                 (move, jog, get_position,
                                                               get_state)
```

**Coupling rule enforced in each subsystem:**

| Subsystem | Imports from motion layer | Imports toolhead? | Imports homing? |
|-----------|--------------------------|-------------------|-----------------|
| `ToolheadManager` | None | — | No |
| `HomingManager` | `MotionClientProtocol` | No | — |
| `MotionEngine` | `MotionClientProtocol` only | No | No |
| `MotionPlatformController` | All three subsystems | Yes (reads geometry) | Yes (reads limits) |

**Cross-subsystem interactions owned by the controller:**

- `set_toolhead(name)` → `ToolheadManager.set_toolhead(name)` then `HomingManager.invalidate_state()` — controller wires the invalidation that previously lived inside the toolhead setter itself.
- `jog()` in homing mode → `HomingManager.homing_jog_update(dx, dy, dz)` (kinematic reset) then `MotionEngine.jog(dx, dy, dz, speed)` (actual G0) — the two responsibilities are now in separate calls.
- `_restore_state()` → `HomingManager.restore()` returns a `str` toolhead name; controller passes it to `ToolheadManager.set_toolhead()` — HomingManager never imports ToolheadManager.
- `home_auto()` → controller checks `ToolheadManager.toolhead.requires_manual_homing`, then passes `self._safe_clearance_z` (a float) to `HomingManager.home_auto(safe_clearance_z)` — HomingManager needs no toolhead reference.
- `save_and_park()` → controller parks via `MotionEngine`, then calls `HomingManager.save(toolhead_name=ToolheadManager.name)` — toolhead name crosses the boundary as a plain string.
- `_safe_clearance_z` and `_check_bounds` — both read from HomingManager (limits) and ToolheadManager (geometry); neither subsystem computes these, the controller does.

---

### Separation of Concerns Assessment

| Concern | Before | After |
|---------|--------|-------|
| Toolhead config loading | Mixed into controller | `ToolheadManager` only |
| Mount state | Mixed into controller | `ToolheadManager` only |
| Axis limits | Mixed into controller | `HomingManager` only |
| Homing state machine | Mixed into controller | `HomingManager` only |
| Kinematic-reset jog trick | Inline in `jog()` | `HomingManager.homing_jog_update()` — clearly named and isolated |
| JSON persistence | Mixed into controller | `HomingManager.save/restore/invalidate_state()` |
| Safe clearance travel sequence | Mixed into controller | `MotionEngine.move_to()` |
| Cross-subsystem offset math | Mixed into controller | Still in controller — correct, as it requires both toolhead geometry and axis limits |
| Cross-subsystem bounds checking | Mixed into controller | Still in controller — correct, same reason |

**What the controller is now:** a coordinator that reads two subsystems (HomingManager for limits, ToolheadManager for geometry), performs the two derived calculations that span both (`_safe_clearance_z`, `_check_bounds`, and offset compensation in `move_to`), and delegates everything else. It contains no state of its own — all mutable state lives in the three subsystems.

**What was not moved and why:** `_check_bounds` and `_safe_clearance_z` are the only logic items left in the controller. Both require data from HomingManager (axis limits, z_min) AND ToolheadManager (footprint, tip_offset_z) simultaneously. Moving either into a subsystem would create a cross-dependency between HomingManager and ToolheadManager that would violate the isolation rules. The controller is the correct home for calculations that cross subsystem boundaries.

---

### Future Toolhead Scaling Assessment

**Adding a new toolhead type (e.g. pipette, gripper, camera mount)**

1. Drop a folder under `io/toolheads/` with a YAML matching the `toolhead_config_template.yaml` schema.
2. `ToolheadManager.list_toolheads()` discovers it automatically — zero Python changes.
3. If the toolhead needs a new geometry field (e.g. `nozzle_diameter`), add it to `ToolheadGeometry` and `toolhead_config.py`. `ToolheadManager` is the only code to update — HomingManager and MotionEngine are unaffected.

**Adding a toolhead that changes homing behavior**

`requires_manual_homing` and `requires_manual_z` are already first-class fields in `ToolheadGeometry`. The check in `MotionPlatformController.home_auto()` reads `ToolheadManager.toolhead.requires_manual_homing`. Adding a new homing-behavior flag follows the same pattern: add the field to YAML + `ToolheadGeometry`, read it in the controller's homing delegation methods. HomingManager is not touched.

**Adding a second motion platform (different gantry)**

The refactor exposes a clean seam: `MotionEngine` and `HomingManager` both depend only on `MotionClientProtocol`. A new gantry requires only:
1. A new client satisfying `MotionClientProtocol` (nine methods).
2. Optionally, a new `HomingManager` subclass if the homing procedure differs (e.g. no endstop, optical homing).
3. `MotionEngine` is unchanged — it only knows the safe travel sequence.
4. `ToolheadManager` is unchanged — toolheads are hardware-agnostic geometry.

**Adding a toolhead with its own sensor (e.g. integrated force probe) *(IMPLEMENTED)***

`ToolheadGeometry` now declares `sensor_type: str | None`. `MotionPlatformController` accepts a `sensor_registry: dict[str, Any]` at construction and exposes `get_toolhead_sensor() -> Any`, which returns the registered sensor for the active toolhead's `sensor_type`, or `None`. `ToolheadManager`, `HomingManager`, and `MotionEngine` are untouched.

To add a new sensor-bearing toolhead:
1. Implement a driver + `Protocol` interface in `io/` (e.g. `ForceProbeProtocol`).
2. Add `sensor_type: force` to the toolhead YAML.
3. Pass `sensor_registry={"force": ForceProbeInstance()}` to `MotionPlatformController` in `__main__.py`.
4. In the SiLA feature, call `controller.get_toolhead_sensor()` and cast to `ForceProbeProtocol`.

The `ph_probe` toolhead already declares `sensor_type: ph`. Wiring up `AtlasPHSensor` to `sensor_registry={"ph": ...}` in `__main__.py` is the only remaining step to activate pH reading through this seam.

**What still doesn't scale: multiple simultaneous toolheads**

`ToolheadManager` holds a single active toolhead. A future multi-head gantry (two independent carriages) would require a `ToolheadManager` that holds a dict of active heads keyed by carriage ID, and `MotionPlatformController` would need to pass a carriage ID to `move_to`. This is a deliberate non-requirement for the current single-carriage SV08 platform and is the expected extension point if the platform grows.

---

## Dynamic Discovery Architecture

*June 2026 — replaced `_KNOWN_FEATURES` probe loop with `SiLAService.GetImplementedFeatures`.*

### Feature → Descriptor → Frontend Tab pipeline

```
SiLAService.GetImplementedFeatures          (always present — mandatory SiLA2 core feature)
  │  returns list[str] of fully-qualified feature identifiers
  │  e.g. ["org.silastandard/core/SiLAService/v1",
  │         "edu.iastate.ames/chembench/MotionPlatform/v0"]
  ▼
_FEATURE_REGISTRY  (sila_client.py)
  │  list[FeatureDescriptor(name, identifier)]
  │  filters server identifiers to display names the client knows how to handle
  │  e.g. "edu.iastate.ames/chembench/MotionPlatform/v0" → "Motion Platform"
  ▼
features_discovered  Qt signal  (emits list[str] of display names)
  ▼
MainWindow._on_features_discovered(features: list[str])
  │  inserts/removes tabs based on display name
  └─ "Motion Platform" → _build_motion_tab() → QTabWidget
```

### What changed

| Before | After |
|--------|-------|
| `_KNOWN_FEATURES: list[dict]` — hardcoded pkg/svc/probe for each feature | `_FEATURE_REGISTRY: list[FeatureDescriptor]` — identifier + display name + `start_streams` callback |
| `_probe_feature(pkg, svc, method)` — one gRPC call per known feature | `_fetch_implemented_features()` — one call to SiLAService, always succeeds or returns [] |
| `if "Motion Platform" in found:` stream start branch | `fd.start_streams(client, gen)` — callback registered in `FeatureDescriptor` |
| `if "Motion Platform" in new/gone:` tab dispatch branches | `_tab_inject_handlers` / `_tab_remove_handlers` dicts in `MainWindow` |
| Adding a feature required editing probe logic + multiple `if` branches | One `FeatureDescriptor` in `_FEATURE_REGISTRY` + one entry in each handler dict |
| Private `_host` attribute accessed from `MainWindow` | `SilaClient.host` public property |

### Key files

| File | Role |
|------|------|
| `proto/sila_service.proto` | Static proto for SiLAService.GetImplementedFeatures. Standard-defined; no generator needed. |
| `proto/sila_service_pb2.py` | Compiled stubs. Regenerate with `python -m grpc_tools.protoc -I proto --python_out=proto proto/sila_service.proto`. |
| `sila_client.py: _FEATURE_REGISTRY` | One entry per feature the frontend knows how to display. Discovery itself is server-driven. |
| `sila_client.py: _fetch_implemented_features()` | Single gRPC call to `/sila2.org.silastandard.core.silaservice.v1.SiLAService/Get_ImplementedFeatures`. |
| `sila_client.py: _discover_and_stream()` | Intersects server identifiers with registry; emits display names. |

### gRPC path derivation

The SiLAService package is derived from the CDK's `FeatureIdentifier.rpc_package` formula:

```
"sila2." + originator + "." + category + "." + feature.lower() + ".v" + major_version
= "sila2.org.silastandard.core.silaservice.v1"
```

The full method path: `/sila2.org.silastandard.core.silaservice.v1.SiLAService/Get_ImplementedFeatures`

The `MotionPlatform` identifier returned by the server:
```
originator="edu.iastate.ames", category="chembench", class="MotionPlatform", version="0.1"
→ "edu.iastate.ames/chembench/MotionPlatform/v0"
```

---

## Remaining Hardcoded Components

*Updated after Architecture Stabilization Pass, June 2026.*

| Component | Location | Notes |
|-----------|----------|-------|
| `_PKG`, `_SVC` constants | `sila_client.py` | Still required for stream/command method paths — `_method()` uses them. Correct to keep; Motion Platform streams are a concrete implementation detail, not a discovery concern. |
| `_build_motion_tab()` | `main_window.py` | Tab layout for Motion Platform is hand-written. Each new feature still needs a dedicated tab builder. Not yet metadata-driven. |
| Motion Platform proto stubs | `proto/motion_platform_pb2.py` | One proto per feature. New features need their own proto + compiled stub. |
| ~~`X_MAX, Y_MAX, Z_MAX`~~ | ~~`sila_client.py`~~ | **REMOVED** — replaced by `GetLimits` SiLA command + `limits_updated(x_min,x_max,y_min,y_max,z_min,z_max)` signal. |
| ~~`if "Motion Platform" in found:` stream start~~ | ~~`sila_client.py`~~ | **REMOVED** — `FeatureDescriptor.start_streams(client, gen)` callback in registry. |
| ~~`if "Motion Platform" in new/gone:` tab dispatch~~ | ~~`main_window.py`~~ | **REMOVED** — `_tab_inject_handlers` / `_tab_remove_handlers` dicts. |

---

## Path Toward Metadata-Driven UI

The current architecture handles Feature → Descriptor → Frontend Tab, but the tab content is still fully hand-authored. Moving toward metadata-driven UI generation requires two additional layers.

### Layer 1: Feature-scoped stream/command registry *(IMPLEMENTED)*

`FeatureDescriptor` now carries a `start_streams` callback (stream startup) and tab injection/removal is handled via `_tab_inject_handlers` / `_tab_remove_handlers` dicts in `MainWindow`:

```python
@dataclasses.dataclass(frozen=True)
class FeatureDescriptor:
    name: str
    identifier: str
    start_streams: Callable[["SilaClient", int], None]  # gen-scoped, called after discovery
```

The `if "Motion Platform"` branches are gone from both `_discover_and_stream` and `_on_features_discovered`. Adding a second feature requires only one new `FeatureDescriptor` in `_FEATURE_REGISTRY` plus a new entry in the inject/remove handler dicts in `MainWindow`. No `if` branches to touch.

### Layer 2: FDL-driven widget generation

The SiLAService exposes `GetFeatureDefinition(identifier)` which returns the FDL (Feature Definition Language) XML for any implemented feature. This XML describes:
- All commands and their parameter types/constraints
- All observable/unobservable properties and their data types
- All defined execution errors

A UI generator could read this XML and produce a generic "commands + properties" tab for any feature without a hand-authored tab builder. This is the correct foundation for a metadata-driven UI:

```
GetFeatureDefinition(identifier)
  │  returns FDL XML
  ▼
Parse FDL → list of commands, properties, data types
  ▼
GenericFeatureTab: auto-generated QWidget with one button per command,
                   one display row per observable property
```

**Pre-conditions before this is feasible:**
- Parameter types in FDL must be parseable to Qt input widgets (float → QDoubleSpinBox, string → QLineEdit, enum → QComboBox)
- Valid ranges and units from FDL constraints must map to widget validators
- Complex structure types (e.g. Position, ToolheadInfo) need either flattened display or a registered custom renderer

The `GetFeatureDefinition` call already works — only the FDL parser and widget generator are missing.

---

## Path Toward AI-Assisted Device Onboarding

### Current state

The `_FEATURE_REGISTRY` is the one remaining manual step when adding a new instrument: a developer must write a `FeatureDescriptor` entry. Everything before that (backend feature registration, SiLA protocol exposure, CDK FDL generation) is already server-side. Everything after (tab generation) could become metadata-driven via Layer 1 and Layer 2 above.

### Minimal AI onboarding loop (near-term)

Given a new instrument (e.g. a conductivity probe):

1. **AI generates the backend feature** — writes a `ConductivitySensor(sila.Feature)` class following CDK patterns (`@sila.ObservableProperty`, `@sila.UnobservableCommand`). The Driver → Sensor → Feature pattern is explicit enough for an AI to follow from existing examples.

2. **AI generates the YAML toolhead/config** — if the instrument has a toolhead, the schema in `toolhead_config_template.yaml` provides the contract. An AI can fill it from a datasheet.

3. **AI adds one `FeatureDescriptor` entry** — `_FEATURE_REGISTRY` in `sila_client.py`. This is the only frontend file that needs editing for discovery.

4. **Server restart** — `GetImplementedFeatures` now returns the new identifier. The frontend picks it up on next connect without any discovery code changes.

### Gap: no `OnboardingFeature` API

Steps 1–3 still require a developer or a code-generating AI with repo access. A future `OnboardingFeature` SiLA service (Phase 6 per migration plan) would accept a JSON device description, validate it against pydantic schemas, write the config, and hot-reload the feature registry — eliminating the need for any code changes at all.

### Gap: no pydantic validation on configs

AI-generated `ToolheadConfig` YAMLs cannot be automatically validated before use. A wrong field name fails silently. Migrating `ToolheadConfig` to a pydantic model (Phase 5 per migration plan) produces a JSON Schema that an AI can treat as the exact contract for generating new configs — with automatic validation on load.

### What the CDK already provides for AI

The CDK's FDL generation (`@sila.ObservableProperty`, `@sila.UnobservableCommand`, `@sila.Feature`) produces machine-readable feature descriptions at the SiLA/gRPC layer. `GetFeatureDefinition` exposes this to clients at runtime. An AI writing a new SiLA feature targets these CDK patterns; an AI-generated UI reads CDK-exposed feature metadata. The `BaseSensor` layer is intentionally kept out of this loop — capability metadata belongs at the CDK layer, not the sensor identity layer.

---

## Architecture Stabilization Pass

*June 2026 — four-phase hardening of the SiLA2 + PySide6 stack.*

### Phase 1 — Critical Runtime Fixes

**1a. Blocking I/O in async SiLA handlers — FIXED**

All `MotionPlatform` command and property handlers now use `await asyncio.to_thread(...)` for every call that reaches `MoonrakerClient` (synchronous `requests.post/get`). In-memory reads (`ToolheadManager`, `HomingManager`) are intentionally NOT wrapped — wrapping pure in-memory property reads would add per-yield thread-pool overhead on high-frequency observables with no benefit.

Affected handlers: `position` (observable property), `toolhead_info`, `move_to`, `jog`, `home_auto`, `finish_homing`, `save_and_park`, `get_limits`.

**1b. Ghost stream threads on rapid reconnect — FIXED**

`SilaClient` now maintains `self._gen: int`. Every call to `connect_to()` increments `_gen` and passes the new value to each thread as `my_gen`. Threads exit on the next loop iteration the moment `self._gen != my_gen`. This guarantees at most one active set of stream threads per connection at any time.

```python
# In each stream thread:
while self._gen == gen and not self._stop.is_set():
    ...
```

**1c. Unsafe homing state persistence — FIXED**

`HomingManager` now tracks `self._is_calibrated: bool`. It is set `True` only by `home_auto()` or `finish_homing()`, and reset to `False` on `restore()` (state loaded from disk) or `invalidate_state()`. `save()` raises `RuntimeError` if `_is_calibrated` is `False`, preventing an unverified disk-to-disk round-trip. The JSON file now stores `"is_calibrated"` and `"timestamp"` fields for auditing.

### Phase 2 — Architectural Cleanups

**Feature dispatch callbacks — FIXED**

`FeatureDescriptor` gained a `start_streams(client, gen)` field. The module-level `_start_motion_streams` function is registered against `MotionPlatform`. `_discover_and_stream` calls `fd.start_streams(self, gen)` for each found feature — no `if "Motion Platform"` branch. `MainWindow` replaced the same-named `if` blocks with `_tab_inject_handlers` / `_tab_remove_handlers` dicts.

### Phase 3 — Discovery + Config Hardening

**GetLimits command — ADDED**

Backend: `MotionControllerProtocol.get_limits() -> str` returns `"x_min|x_max|y_min|y_max|z_min|z_max"`. `MotionPlatformController.get_limits()` reads directly from `HomingManager`. The SiLA feature exposes `@sila.UnobservableCommand() async def get_limits() -> str` with `await asyncio.to_thread(...)`.

Proto: `gen_proto.py` updated with `GetLimits_Responses { SString Limits = 1; }` message and `rpc GetLimits`. Both `.proto` and `_pb2.py` regenerated.

Frontend: `SilaClient` removed `X_MAX, Y_MAX, Z_MAX = 350.0, 350.0, 340.0`. `_discover_and_stream` calls `fetch_limits()` after discovery and emits `limits_updated(x_min, x_max, y_min, y_max, z_min, z_max)`. `MainWindow._on_limits_updated` calls `self._grid.set_limits(x_max, y_max)` and `self._zbar.set_limits(z_max)`.

### Phase 4 — Test + Safety Layer

56 smoke tests in `software/backend/tests/`:

| File | Tests | Coverage |
|------|-------|----------|
| `test_motion_controller.py` | 8 | `get_limits`, `move_to` (in-bounds + 3 limit violations), `jog`, save guard, save-after-homing |
| `test_toolhead_manager.py` | 7 | YAML discovery, geometry load, clear, mount state, `sensor_type` exposed/cleared, unknown toolhead |
| `test_well_plate.py` | 20 | 96-well + 24-well: `PlateGeometry` label parsing, coordinate math, `list_available()`, `load()`, out-of-range errors |
| `test_workspace_manager.py` | 13 | `load_from_yaml`, `resolve_well`, standard/rotated_90 orientation, short label, unknown plate, clear |
| `test_feature_discovery.py` | 8 | Exact match, case-insensitive, mixed-case, unknown ignored, empty list, multi-feature, registry uniqueness |

Run with: `make test` (or `PYTHONPATH="" uv run pytest tests/ -v` directly).

`PYTHONPATH=""` is required because the ROS2 Jazzy system Python registers pytest plugins via `entry_points` that conflict with the uv-managed venv. Stripping `PYTHONPATH` removes the `/opt/ros/jazzy/lib/python3.12/site-packages` path before plugin discovery. The `pyproject.toml` `[tool.pytest.ini_options]` addopts also contains `-p no:launch_testing` and related flags as a belt-and-suspenders guard.
