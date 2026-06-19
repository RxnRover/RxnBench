# Automated Chem Bench — Architecture Review

**Date:** June 2026  
**Reviewer:** Architectural analysis of commit `e7c34c9`; updated after interface layer migration  
**Scope:** Full codebase review — all first-party Python source, YAML configs, and tooling

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
| Frontend hardcodes `X_MAX, Y_MAX, Z_MAX = 350, 350, 340` | `software/frontend/src/chem_bench_ui/app.py:38` | These should come from a SiLA property (`GetLimits`) served by `MotionPlatformController`. Phase 3 item. |
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

---

## Current Architecture

### System Topology

```
Operator Machine (Linux/Mac/Win)          Raspberry Pi                   Sovol SV08
──────────────────────────────────        ─────────────────              ─────────────────
chem_bench_ui (PySide6 + gRPC)            chem_bench (SiLA2 server)      H616 ARM (Linux)
  SilaClient                              MotionPlatform feature ──────> Moonraker :7125
  ├─ raw gRPC :50051                      PHSensor feature (disabled)      └─ Klipper
  └─ hand-coded protobuf codec            MotionPlatformController          └─ MCU (serial)
                                          MoonrakerClient                    └─ steppers
                                          AtlasPHSensor (not wired yet)
                                          homing_state.json (~/.chem_bench/)
```

The backend runs on a Raspberry Pi (or any Linux host) and exposes a SiLA2 gRPC server on port 50051. The frontend runs on the operator's machine and connects to that server. The SV08 runs Moonraker on the onboard H616 SoC; the backend drives it over HTTP.

### Module Map

#### Backend (`software/backend/src/chem_bench/`)

| File | Purpose |
|------|---------|
| `__main__.py` | App factory. Discovers Moonraker, wires `MotionPlatformController` into `MotionPlatform` feature, hands to `Connector`. PHSensor and camera are commented-out placeholders. |
| `_cli.py` | `chem-bench` console script. Locates `config.json` and shims into `unitelabs.cdk.cli.connector`. |
| `features/motion_platform.py` | SiLA2 feature. ObservableProperties: `position`, `state`, `toolhead_info`, `has_saved_state`. Commands: `move_to`, `jog`, `engage_tool`, `disengage_tool`, homing suite, toolhead management, `save_and_park`. |
| `features/ph_sensor.py` | SiLA2 feature for pH. Exists and is complete; not registered in `__main__.py`. |
| `features/camera_feature.py` | Empty docstring stub. |
| `io/base_driver.py` | `AbstractI2CDriver` ABC. Handles send/read/delay pattern over I2C so subclasses only implement `_parse_response`. |
| `io/base_sensor.py` | `BaseSensor` ABC + `SensorReading` dataclass. Enforces `read()`. Sensor identity only — capability metadata is owned by the CDK layer. |
| `io/errors.py` | Domain exceptions: `DeviceNotFoundError`, `DeviceCommunicationError`, `CalibrationError`, `MotionLimitError`. |
| `io/interfaces/enums.py` | `CalibrationPoint` enum (pH-specific; co-location will need revisiting as more devices are added). |
| `io/motion_platform/motion_platform_controller.py` | High-level motion controller. Adds toolhead offset compensation, safe clearance travel sequence (raise → XY → lower), bounds checking with footprint margins, and auto/manual homing state machine on top of `MoonrakerClient`. |
| `io/motion_platform/moonraker_client.py` | Synchronous HTTP client for Moonraker REST API (port 7125). POST `/printer/gcode/script` blocks until Klipper completes the move. |
| `io/motion_platform/mock_moonraker.py` | In-memory drop-in for development without hardware. Simulates motion with time-proportional delays. Activated via `CHEM_BENCH_MOCK=1`. |
| `io/motion_platform/moonraker_discovery.py` | Parallel mDNS (`zeroconf`) + IPv6 link-local scan. Returns first responding host. Works for both WiFi and direct Ethernet. |
| `io/motion_platform/homing_state.py` | JSON persistence of calibrated axis limits in `~/.chem_bench/homing_state.json`. Invalidated on unclean exit or toolhead change. |
| `io/ph/atlas_scientific_driver.py` | `AtlasScientificEZO`: raw EZO I2C command set. No pH logic — just protocol. |
| `io/ph/atlas_ph_sensor.py` | `AtlasPHSensor(BaseSensor)`: pH-specific logic (calibration, slope, temperature compensation). Wraps the driver. |
| `io/toolheads/toolhead_config.py` | `ToolheadConfig` + `ToolheadGeometry` dataclasses. Loads from per-toolhead YAML folder. |
| `io/toolheads/ph_probe/ph_probe_toolhead.yaml` | Real toolhead config: 44×25 mm footprint, 110 mm tip depth, 25 mm engage depth. |
| `io/toolheads/toolhead_config_template.yaml` | Template for adding new toolheads. |
| `io/camera/camera_crowsnest_client.py` | 15-line stub. `CrowsnestClient.__init__` only; no HTTP calls. |
| `labware/well_plate.py` | `WellPlate` + sub-dataclasses (`WellLayout`, `PlateDimensions`, `WellGeometry`, `WellSpacing`, `WellOrigin`). Coordinate model with `well_position()`, `well_position_by_label()`, `parse_label()`, `well_label()`, `wells()`, `is_valid()`, `list_available()`. All frozen dataclasses — no hardware or UI dependency. |
| `labware/definitions/96_well_standard/96_well_standard.yaml` | ANSI/SBS 96-well standard (127.76 × 85.48 mm, 9 mm pitch, 8×12, 360 µL). |
| `labware/definitions/24_well_standard/24_well_standard.yaml` | ANSI/SBS 24-well standard (127.76 × 85.48 mm, 19.30 mm pitch, 4×6, 3470 µL). |
| `labware/definitions/well_plate_template.yaml` | Authoring template for new well plate definitions. |

#### Frontend (`software/frontend/src/chem_bench_ui/`)

| File | Purpose |
|------|---------|
| `app.py` (2000 lines) | Monolithic UI. Contains `SilaClient` (gRPC + raw protobuf codec), all widget classes, and `MainWindow`. See widget inventory below. |
| `themes.py` | `DARK`/`LIGHT` color palettes as dicts. `build_qss(t)` generates a QSS stylesheet string. |

**Widget inventory in `app.py`:**

| Class | Role |
|-------|------|
| `SilaClient` | gRPC channel management, raw protobuf encode/decode, Qt signals for position/state/toolhead/connection, background streaming threads. |
| `PositionGrid` | Custom `QPainter` 2D top-down XY canvas. Shows gantry rails, carriage, toolhead footprint, tip crosshair, click-to-move target. |
| `ZBar` | Custom `QPainter` vertical Z indicator. Shows tip depth and engage range markers. |
| `ToolheadPanel` | Compact toolhead selector in the Motion Platform tab. |
| `ToolheadDiagramWidget` | 2D scaled toolhead footprint diagram with mount point, body centre, and tip cross. |
| `ToolheadManagerPanel` | Full Toolheads tab: list, details, mount/unmount, set/clear active. |
| `ServerInfoPanel` | SiLA server status + per-feature discovery badges. |
| `HomingPanel` | Auto-home XY button + step-by-step manual homing workflow with per-axis confirm buttons. |
| `JogPanel` | XY/Z jog buttons, step size presets, keyboard arrow key support. Hidden in user mode. |
| `MainWindow` | Top-level window. Connection bar, dynamic tab injection on feature discovery, error toast, dev/user mode gate, theme switching, Save & Quit. |

### Communication Layer

| Layer | Transport | Details |
|-------|-----------|---------|
| Frontend → Backend | gRPC (insecure, port 50051) | Raw `grpc.Channel` with hand-coded varint/protobuf codec. No generated stubs. ObservableProperties → `unary_stream`. Commands → `unary_unary`. |
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
| Frontend dependencies | `PySide6`, `grpcio`, `zeroconf` |
| SiLA CDK version | `unitelabs-cdk==0.11.2`, `unitelabs-sila==0.8.0` |
| Config | `config.json` (SiLA server identity, TLS off, UUID `a9a1052f`) |

---

## Dependency Graph

```
chem_bench_ui.app
  ├── SilaClient
  │     ├── grpc.Channel ──────────────────────────────────→ chem_bench SiLA server :50051
  │     └── hand-coded varint/protobuf codec
  └── _KNOWN_FEATURES (static list)

chem_bench.__main__  (app factory)
  ├── Connector (unitelabs-cdk)
  └── MotionPlatform feature
        └── MotionPlatformController
              ├── MoonrakerClient ──────────────────────────→ SV08 Moonraker :7125
              │     └── requests.post/get (synchronous)         └─ Klipper → MCU → motors
              ├── MockMoonrakerClient (CHEM_BENCH_MOCK=1)
              ├── ToolheadConfig ──────────────────────────→ io/toolheads/*/name_toolhead.yaml
              └── homing_state ───────────────────────────→ ~/.chem_bench/homing_state.json

PHSensor feature  [NOT REGISTERED in __main__.py]
  └── AtlasPHSensor (BaseSensor)
        └── AtlasScientificEZO (AbstractI2CDriver)
              └── i2c_bus  [NOT INSTANTIATED — smbus2 call missing]

WellPlate ──────────────────────────────────────────────→ labware/definitions/*/name.yaml
  [NOT CONNECTED TO ANY FEATURE OR WORKFLOW — Phase 3 item]
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
`_KNOWN_FEATURES` + `_on_features_discovered` inserts and removes UI tabs based on what the server reports. The UI is not hardwired to a fixed feature set at compile time.

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

**3. Blocking synchronous I/O in async SiLA handlers**
`MotionPlatform.move_to()` is `async def` but calls `self._controller.move_to(x, y, z)` which in turn calls `requests.post(...)` — a blocking network call. This blocks the asyncio event loop for the full duration of every move, preventing other SiLA requests from being processed concurrently.

**4. Frontend is a 2000-line monolith**
`app.py` mixes gRPC connection management, raw protobuf codec, domain models (`ToolheadInfo`), all widget classes, and `MainWindow`. Every new SiLA feature requires adding more to this single file. It will not scale beyond two or three features.

**5. Hand-coded protobuf in the frontend**
Varint encoding and field-number constants are inlined in `app.py`. Every schema change in SiLA type definitions (field order, new fields) requires a corresponding manual update to the codec. The comment "no generated stubs needed" is accurate but trades maintenance friction for setup simplicity.

**6. Well plates are not connected to anything**
`WellPlate` (`labware/well_plate.py`) is complete with coordinate model, label parsing, and well iteration, but has no SiLA feature, no workflow, and no UI. A motion command currently requires raw XYZ coordinates. The system cannot express "move to well A3 of plate P." Phase 3 adds the SiLA `WellPlate` feature.

**7. `CalibrationPoint` enum lives in `interfaces/enums.py` but is pH-specific**
As more devices are added, this shared file risks becoming a dumping ground for unrelated enums. Device-specific enums should live co-located with their device modules.

**8. Frontend hardcodes machine axis limits**
`X_MAX, Y_MAX, Z_MAX = 350.0, 350.0, 340.0` at the top of `app.py` duplicates information that lives in the server's `MotionPlatformController`. If the motion platform changes (or limits are calibrated differently), the frontend must be edited separately.

**9. I2C bus is never instantiated**
The path from the Raspberry Pi's I2C bus to `AtlasPHSensor` is fully designed but the `smbus2.SMBus(1)` call that would wire it up is absent from `__main__.py`. There is no mock I2C bus for development either.

**10. Frontend accesses a private attribute**
`_on_connected` in `MainWindow` uses `self._client._host`, directly accessing a private attribute of `SilaClient`. This should be a public property.

**11. No test coverage**
No test files exist in the first-party source tree. The mock infrastructure is in place but is not exercised by any automated tests.

**12. No TLS in the production config**
`config.json` has `"tls": false`. Acceptable for isolated development, but requires a plan before lab deployment.

---

## Technical Debt

| Item | Location | Severity |
|------|----------|----------|
| pH probe `tip_x`/`tip_y` have TODO comments — offsets not yet measured | `io/toolheads/ph_probe/ph_probe_toolhead.yaml:9-10` | Low |
| `camera_feature.py` is an empty docstring — no implementation | `features/camera_feature.py` | Low |
| `CrowsnestClient` is a stub with no HTTP logic | `io/camera/camera_crowsnest_client.py` | Low |
| `interfaces/__init__.py` is empty | `io/interfaces/__init__.py` | Trivial |
| `features/__init__.py` is empty | `features/__init__.py` | Trivial |
| `chem_bench/__init__.py` is empty | `__init__.py` | Trivial |
| PHSensor feature not registered — no smbus2 instantiation path | `__main__.py:47-49` | Medium |
| Frontend accesses `_client._host` (private attribute) | `app.py:1962` | Low |
| Machine axis limits duplicated between server config and frontend constant | `app.py:38`, config.json | Medium |
| `WellPlate` has no SiLA feature, workflow, or UI connection | `labware/well_plate.py` | Medium |

---

## Risks

| Risk | Location | Impact | Likelihood |
|------|----------|--------|------------|
| Blocking `requests.post()` in `async def` SiLA handlers stalls the event loop during every move | `moonraker_client.py`, `motion_platform.py` | **High** — server becomes unresponsive to all other requests during motion | Certain |
| Homing state can be saved with default (uncalibrated) axis limits, silently loading incorrect bounds on next boot | `motion_platform_controller.py:342`, `homing_state.py` | **Medium** — incorrect motion envelope on restart | Low but serious |
| Ghost threads on rapid reconnect — old stream threads may still be running when new ones start | `app.py:SilaClient` | **Medium** — duplicate position updates, stale state | Occasional |
| ~~`MockMoonrakerClient` can silently diverge from `MoonrakerClient` without a shared Protocol~~ **FIXED** — `MotionClientProtocol` enforces the shared surface | — | Resolved | — |
| ~~PHSensor feature imports `AtlasPHSensor` directly~~ **FIXED** — feature now accepts `PHSensorProtocol` | — | Resolved | — |
| No TLS — bare gRPC on any network the Pi is on | `config.json` | **Low** in isolated lab network, **High** if shared | Context-dependent |

---

## Recommended Migration Order

### Phase 1 — Interface contracts and async correctness (Week 1)

These are the highest-risk items. Fix them before adding new features.

1. ✅ **Define `MotionClientProtocol` and `MotionControllerProtocol`** — done. Both live in `io/interfaces/motion.py`. `motion_platform_controller.py` now depends on `MotionClientProtocol`; `features/motion_platform.py` depends on `MotionControllerProtocol`.

2. **Fix blocking I/O** — wrap all `MoonrakerClient` calls in `asyncio.to_thread()` inside the SiLA feature methods. This is one line per command but eliminates the event-loop stall risk entirely.

3. ✅ **Decouple `PHSensor` from concrete class** — done. `PHSensor.__init__` now accepts `PHSensorProtocol` (`io/interfaces/ph_sensor.py`). Atlas-specific pH-only methods (`slope`) are included in the protocol.

4. **Expose `SilaClient.host` as a public property** — remove the `_host` private-access in `MainWindow._on_connected`.

### Phase 2 — Complete the sensor chain (Week 1-2)

5. **Wire up `AtlasPHSensor` in `__main__.py`** — add smbus2 bus instantiation (or a mock I2C bus under `CHEM_BENCH_MOCK=1`) and register `PHSensor` feature. This is the path to any chemistry measurement.

6. **Add mock I2C bus** — a `MockI2CBus` alongside `MockMoonrakerClient` so the full feature set (motion + pH) works in mock mode without any hardware.

7. **Implement basic `CrowsnestClient`** — MJPEG snapshot via `requests.get`. Register a minimal camera SiLA feature.

### Phase 3 — Well plate workflow layer (Week 2)

8. **Add `WellPlate` SiLA feature** — exposes `ListPlates`, `SetPlate(name)`, `MoveTo(label)`. Uses `WellPlate.well_position_by_label()` to translate well addresses to XYZ, then delegates to `MotionPlatformController.move_to()`.

9. **Expose plate overlay in the frontend** — when a plate is set, draw the plate footprint and well grid on `PositionGrid`. Click-to-move snaps to the nearest well center.

10. **Read axis limits from the server** — replace hardcoded `X_MAX, Y_MAX, Z_MAX` in `app.py` with a call to a new `GetLimits` SiLA property or the `DeviceInfo` feature (Phase 5).

### Phase 4 — Frontend decomposition (Week 2-3)

11. **Split `app.py`** into focused modules:
    - `sila_client.py` — gRPC connection, streaming threads, command fire methods
    - `protobuf.py` — varint/codec helpers
    - `domain.py` — `ToolheadInfo` and other shared dataclasses
    - `widgets/position_grid.py`, `widgets/z_bar.py`
    - `panels/homing.py`, `panels/jog.py`, `panels/toolhead.py`, `panels/server.py`
    - `app.py` — `MainWindow` + `main()` only

12. **Add pytest scaffold** — cover `MotionPlatformController` (mock client), `ToolheadConfig`/`WellPlateConfig` loading, and the protobuf codec.

### Phase 5 — Metadata-driven UI foundation (Week 3)

13. **Add `DeviceInfo` SiLA feature** — returns structured JSON describing all registered features, sensor manifests, toolhead list, and plate list. The frontend queries this on connect instead of using `_KNOWN_FEATURES`.

14. **Migrate `_KNOWN_FEATURES` to server-sourced discovery** — the frontend asks the server "what features do you have?" rather than guessing from a static list.

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
| UI adapts to discovered features | ✅ `_on_features_discovered` inserts tabs | Driven by a static `_KNOWN_FEATURES` list, not server introspection |
| New instruments require minimal code | ⚠️ Backend: YAML drop-in | Frontend: requires new widget + `_KNOWN_FEATURES` entry |
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

| Week | Focus | Key Deliverables |
|------|-------|-----------------|
| **Week 1** | Interface contracts + async correctness | `MoonrakerClientProtocol`, `asyncio.to_thread` wrapping in motion feature, `PHSensor` decoupled from concrete class, `SilaClient.host` property, pytest scaffold |
| **Week 2** | Sensor chain + well plate layer | `AtlasPHSensor` wired in `__main__.py`, mock I2C bus, `PHSensor` registered, basic `CrowsnestClient`, `WellPlate` SiLA feature, plate overlay in `PositionGrid` |
| **Week 3** | Frontend decomposition + `DeviceInfo` | `app.py` split into modules, `DeviceInfo` SiLA feature, server-sourced axis limits, pydantic `ToolheadConfig`/`WellPlateConfig`, test coverage for controller + configs |
| **Week 4** | AI onboarding scaffold + polish | JSON manifest schemas, `OnboardingFeature` SiLA service, TLS config guide, end-to-end mock-mode test run |

### Approximate scope per week

- Week 1: ~4 files changed, ~200 lines net. No new features — safety and correctness only.
- Week 2: ~6 new files, ~500 lines. First chemistry measurement visible in the UI.
- Week 3: ~10 files refactored + 2 new, ~400 lines net. Frontend becomes navigable.
- Week 4: ~4 new files, ~600 lines. Lays the AI-onboarding foundation without requiring an AI to exist yet.

---

*Generated from a full read of the codebase at commit `e7c34c9`. Source code was not modified.*

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
