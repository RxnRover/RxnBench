# Rxn Bench — Current State

**Last cleaned:** July 1, 2026  
**Purpose:** Keep the active architecture, current gaps, and next engineering moves visible without preserving every historical migration note.

---

## 1. Architecture Snapshot

Rxn Bench is a modular lab automation stack built around separate SiLA device servers and a PySide6 operator UI.

```text
Operator Machine
└── rxn_bench_ui  ── gRPC/SiLA ── Raspberry Pi
    ├── core shell              ├── rxn-bench-gantry :50051 ── Moonraker/Klipper/SV08
    ├── device plugins          └── rxn-bench-ph     :50052 ── pH sensor stack
    └── experiment scripts
        └── rxn_bench_client
```

The backend is split into independently deployable packages:

| Package | Role | Notes |
|---|---|---|
| `rxn_bench_gantry` | Gantry SiLA server | Motion, homing, workspace/well movement, toolhead management, Moonraker bridge |
| `rxn_bench_ph` | pH SiLA server | pH readings, calibration, slope reporting, mock pH path |
| `rxn_bench_client` | Experiment script client | Script-friendly session manager and instrument wrappers |
| `rxn_bench_template` | Device template | Reference package for adding future device servers |

The frontend is a PySide6 app with a stable split between core shell code and per-device plugins.

Per-package class/package UML diagrams (generated via `make uml`, see each package's `docs/Makefile`) are checked in at [docs/architecture/uml/](../architecture/uml/).

### Device-first layout

Each device is a self-contained top-level folder, not split across the `software/backend` and `software/frontend` trees:

```text
devices/
├── gantry/
│   ├── backend/    ← rxn_bench_gantry SiLA server package
│   └── frontend/   ← gantry device plugin (widget + connection layer)
├── ph_sensor/
│   ├── backend/    ← rxn_bench_ph SiLA server package
│   └── frontend/   ← pH device plugin
└── device_template/
    ├── backend/    ← reference backend package for new devices
    └── frontend/   ← reference frontend plugin for new devices
```

This is a file-layout convention only — it does **not** relax the hard machine-separation rule below. `devices/<name>/backend/` still only ships to the Raspberry Pi; `devices/<name>/frontend/` still only runs on the operator machine as part of the single `rxn_bench_ui` app; nothing under `frontend/` imports anything under `backend/`. `software/backend/` (uv workspace root, `client/`, `install.sh`) and `software/frontend/` (the app itself: `core/`, `connections/`, `proto/`) hold the code that isn't specific to one device.

---

## 2. Frontend Layout

```text
software/frontend/src/rxn_bench_ui/
├── app.py
├── discovery.py
├── themes.py
├── proto/
│   ├── motion_platform.proto
│   ├── motion_platform_pb2.py
│   └── sila_service_pb2.py
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
├── assets/
└── ui/

devices/ph_sensor/frontend/
├── __init__.py
├── connection_spec.yaml
├── generated_connection.py
├── connection.py
├── widget.py
└── ui/
```

### Frontend rule

Each device plugin owns its own widget and connection layer. Core only handles application shell behavior, discovery, device selection, workspace tabs, theme propagation, and generic fallback UI.

### Device plugin contract

Each device's `devices/<name>/frontend/__init__.py` exports:

```python
FEATURE_FRAGMENTS: list[str]
def create_widget(server, theme: dict) -> QWidget: ...
```

`rxn_bench_ui/devices/__init__.py`'s `all_devices()` discovers plugins dynamically by scanning `devices/*/frontend/` at the repo root and loading each `__init__.py` as `rxn_bench_ui.devices.<name>` via `importlib.util.spec_from_file_location` (so their relative imports, e.g. `from ...discovery import ...`, resolve normally). `core/device_registry.py` just calls `all_devices()`. Adding a new frontend device should not require editing the core registry.

---

## 3. Connection Layer Pattern

The frontend connection layer is intentionally split into generated boilerplate and handwritten behavior.

| File | Purpose |
|---|---|
| `devices/<name>/frontend/connection_spec.yaml` | Human-authored manifest of streams, signals, decode types, and commands |
| `devices/<name>/frontend/generated_connection.py` | Generated Qt signals, stream startup, and typed command wrappers |
| `devices/<name>/frontend/connection.py` | Human-maintained subclass with decode handlers, convenience methods, and workflows |
| `software/frontend/src/rxn_bench_ui/connections/base.py` | Shared gRPC channel lifecycle, reconnect handling, stream cancellation, `_spawn_stream()`, `_call()`, and `_fire()` |

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

`software/backend/pyproject.toml` is still the uv workspace root and still owns the shared dev venv, `Makefile`, `install.sh`, and `scripts/install_service.sh` — but its `[tool.uv.workspace] members` now point out to `../../devices/<name>/backend` instead of holding the packages directly. `client/` is not a device and stays inside `software/backend/`.

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
├── atlas_scientific_driver.py
├── base_sensor.py
├── base_driver.py
├── mock_ph_sensor.py
├── enums.py
└── session_log.py
```

Main responsibilities:

- Expose the pH SiLA feature.
- Keep pH feature logic decoupled from concrete sensor implementation through `PHSensorProtocol`.
- Support mock pH readings for development.
- Keep pH-specific calibration concepts inside the pH package.

### Client package

```text
software/backend/client/src/rxn_bench_client/
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
| Frontend pH connection | Done, but still uses temporary hand-rolled protobuf helpers |
| Shared frontend connection base | Done |
| Per-device generated connection layer | Done |
| Session JSONL logs | Done |
| CSV viewer and experiment notes panels | Done |
| Multi-tab frontend workspaces | Done |
| `SiLAService.GetImplementedFeatures` discovery | Done |
| Proto drift check for gantry | Done |
| Split-service install/systemd scripts | Done |
| Device-first repo layout (`devices/<name>/{backend,frontend}`) | Done |
| `device_template` frontend half (was backend-only) | Done |
| `motion_platform.proto` matches backend dataclasses/feature | Done |
| pH backend real test suite (driver, sensor, feature layers) | Done |

---

## 6. Current Gaps

These are the active issues worth tracking now.

| Gap | Location | Priority | Notes |
|---|---|---:|---|
| Add real pH I2C wiring | `rxn_bench_ph/server.py` | High | Instantiate `smbus2.SMBus(1)` and wire it into `AtlasScientificEZO` / `AtlasPHSensor` for real hardware mode. |
| Add mock I2C bus | `rxn_bench_ph/` | Medium | Needed for end-to-end mock-mode testing of the real pH driver path. |
| Generate pH protobuf stubs | frontend `proto/` + backend pH generator path | Medium | Replace temporary pH varint/LEN helpers with generated stubs like the gantry path. |
| Add plate overlay to gantry canvas | `devices/gantry/frontend/` | Medium | Show plate footprint and well grid in `PositionGrid`. |
| Migrate configs to pydantic | gantry config models | Medium | Gives validation, clearer errors, and JSON Schema export. |
| Add TLS deployment guide | docs/config | Low until shared-network deployment | Bare gRPC is acceptable for isolated bench development but not for a shared lab network. |
| Measure pH probe `tip_x` / `tip_y` | `toolheads/ph_probe/ph_probe_toolhead.yaml` | Low | Current values are placeholders. |
| Camera support | new package/device | Low | Phase 2+ feature, not part of current bench core. |
| Experiment-lock RPCs not yet wired into the frontend | `devices/gantry/frontend/` | Medium | `AcquireExperimentLock`/`PauseExperiment`/`ResumeExperiment`/`StopExperiment`/`GetExperimentState`/`ExperimentActive` exist on the backend and now have generated proto stubs, but nothing in the gantry frontend widget/connection calls them yet — the UI can't currently show or control experiment-lock state. |

---

## 7. Immediate Next Work

1. Wire the real pH hardware path:
   - instantiate the I2C bus
   - wire `AtlasScientificEZO`
   - wire `AtlasPHSensor`
   - preserve mock mode

2. Add `MockI2CBus` so pH can be exercised end-to-end without hardware.

3. Generate pH protobuf stubs and remove temporary hand-rolled wire encode/decode from the frontend pH connection.

4. Add plate overlay rendering to the gantry frontend.

5. Start pydantic migration for config models:
   - `ToolheadConfig`
   - `WorkspaceConfig`
   - `MachineConfig`
   - labware definitions

---

## 8. Stable Design Decisions

- Keep one backend package per physical/logical device.
- Keep one SiLA server process per device.
- Keep each device self-contained as one `devices/<name>/{backend,frontend}` folder at the repo root (a "drop in or remove" unit), while the SiLA/gRPC machine-separation boundary and the uv-workspace/single-frontend-app mechanics stay exactly as before — this is a file-layout change, not an architecture change. `software/backend/` and `software/frontend/` hold the non-device-specific app/workspace machinery only.
- Keep shared connection lifecycle code in `connections/base.py`.
- Keep generated connection code next to the device it belongs to.
- Keep widgets handwritten.
- Keep workflows handwritten.
- Keep device discovery server-sourced through `SiLAService.GetImplementedFeatures`.
- Keep toolhead and labware definitions YAML/config-driven.
- Keep experiment scripts using `rxn_bench_client` rather than directly depending on frontend code.
- Keep the shared uv workspace venv for local dev/test only. Production deployment gives gantry and ph_sensor their own standalone venv each (via `scripts/install_service.sh`), so either service can be updated/restarted without affecting the other.

---

## 9. Platform Roadmap

**Long-term goal:** grow Rxn Bench from a single bench (gantry + pH) into more of an allround laboratory control platform — many/heterogeneous devices, not just this one bench. This doesn't change anything in sections 1-8; the device-first layout, one-SiLA-server-per-device model, and mock/real hardware split already scale toward this goal without rework.

Near-term, in priority order:

1. **Workflow runner in `rxn_bench_client` — not a YAML DSL, a thin structural layer over plain Python scripts.** Experiment scripts stay arbitrary Python (loops, conditionals, numpy/pandas, adaptive logic) — that expressiveness is worth keeping, not replacing. What's missing is a lightweight decorator/context-manager per step that gives a `WorkflowRunner` enough structure to: retry/resume from the failed step instead of rerunning the whole script, know which devices a step touches before running it (so a future scheduler can avoid device contention), and record a structured per-step audit trail alongside the existing JSONL session logs. Pure Python, no new service or database; lives inside the existing client package. (MADSci itself does the analogous thing — YAML workflows plus an escape-hatch `ExperimentApplication` Python class — because pure declarative workflows aren't enough either.)
2. **Generic FDL-driven device widget** (see `FUTURE_IDEAS.md` §1). Needed before device count grows past what's hand-maintainable: parse `SiLAService.GetFeatureDefinition()` and auto-generate a basic property/command panel, so a new device — including third-party commercial SiLA2 instruments — is usable the moment it's discovered, without a frontend dev cycle first.
3. **Prove the pattern with a real third device** (camera is already parked as the next device in `FUTURE_IDEAS.md` §5). Bar to clear: adding it touches only a new `devices/camera/{backend,frontend}` folder — nothing in `core/` or `device_registry.py`. If that's not true, fix the abstraction before adding a 4th/5th device.

Deferred until a concrete trigger (not speculative work — see `FUTURE_IDEAS.md` for design notes on several of these):

| Capability | Build when... |
|---|---|
| Resource/labware/inventory tracking | Juggling enough reagents/labware that a human can't track it by eye |
| Multi-bench discovery + TLS | A second physical bench/room actually exists (today's mDNS discovery is local-subnet only) |
| Autonomous experiment loop (`FUTURE_IDEAS.md` §2-4) | Unattended overnight runs are actually wanted, not just multi-instrument human-supervised control |

---

## 10. Deferred Ideas

The following ideas are intentionally moved out of the active architecture plan and into `FUTURE_IDEAS.md`:

- generic FDL-driven UI generation
- AI-assisted device onboarding
- runtime `OnboardingFeature`
- hot-reloadable generated device manifests
- fully metadata-driven workflow generation
- camera package/design exploration

These are interesting, but they should not block the current bench from becoming stable, installable, and testable.
