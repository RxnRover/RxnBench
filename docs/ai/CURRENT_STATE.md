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
| Generic FDL-driven device inspector (`GenericDeviceWidget`) | Done, including dynamic FDL→protobuf construction, structured/list params, observable commands, typed input widgets — see `FUTURE_IDEAS.md` §1 |
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
| Gantry backend real test suite (motion engine sequencing, homing state machine, toolhead-aware bounds, controller, feature, well/workspace math, mock Moonraker) | Done |
| Experiment-lock frontend visibility | Done — banner + Pause/Resume/Stop wired to `experiment_active_changed` in the main widget (`_set_controls_locked` disables toolhead-management buttons, including the ones that launch the Homing/Toolhead Calibration dialogs). Homing and Toolhead Calibration dialogs also now disable their own jog/confirm controls if the lock is acquired while already open. Backend-level RPC gating (a direct call bypassing the UI) is a separate, still-open gap — see §6. |
| `generated_connection.py` drift check | Done — `make check-connections` (new `software/frontend/Makefile`) regenerates every device's `generated_connection.py` from its `connection_spec.yaml` and diffs; `make gen-connections` regenerates in place. Loops over `devices/*/frontend/connection_spec.yaml` generically, so it covers new devices automatically. |
| `motion_platform` proto stubs live under `devices/gantry/frontend/proto/` | Done, moved out of the shared `proto/` tree, which now only holds `sila_service_pb2` (framework-level, genuinely shared). `gen_proto.py`, the `software/backend/Makefile` proto targets, and `connection_spec.yaml`'s `proto_module` all point at the new location; `make check-proto` still passes |

---

## 6. Current Gaps

These are the active issues worth tracking now.

| Gap | Location | Priority | Notes |
|---|---|---:|---|
| Add real pH I2C wiring | `rxn_bench_ph/server.py` | High | Instantiate `smbus2.SMBus(1)` and wire it into `AtlasScientificEZO` / `AtlasPHSensor` for real hardware mode. |
| Add mock I2C bus | `rxn_bench_ph/` | Medium | Needed for end-to-end mock-mode testing of the real pH driver path. |
| Generate pH protobuf stubs | `devices/ph_sensor/frontend/proto/` + backend pH generator path | Medium | Replace temporary pH varint/LEN helpers with generated stubs like the gantry path. Stub placement is now settled: land them in `devices/ph_sensor/frontend/proto/`, matching the per-device placement gantry now uses (see §5), not the shared core `proto/` tree. |
| Add plate overlay to gantry canvas | `devices/gantry/frontend/` | Medium | Show plate footprint and well grid in `PositionGrid`. |
| Migrate configs to pydantic | gantry config models | Medium | Gives validation, clearer errors, and JSON Schema export. |
| Entry-points plugin refactor for frontend device discovery | `rxn_bench_ui/devices/__init__.py` | Medium | Current `all_devices()` loader uses `importlib.util.spec_from_file_location` to scan `devices/*/frontend/` at the repo root. Should land before device #3: turn each `devices/<name>/frontend/` into a small installable package exposing an entry point in a `rxn-bench-ui.devices` group, discovered via `importlib.metadata`, symmetric with the backend's uv workspace members. Not attempted in this pass — file-location scanning still works for two devices. |
| Add TLS + authentication deployment guide | docs/config | Low until shared-network deployment | Bare, unauthenticated gRPC is acceptable for isolated bench development but not for a shared lab network. Note: Moonraker's own HTTP API on the Pi is itself unauthenticated by default, so network exposure bypasses *all* gantry safety logic (bounds, clearance, experiment lock) the moment this leaves an isolated bench network — TLS on the SiLA/gRPC layer alone would not close that hole. |
| Measure pH probe `tip_x` / `tip_y` | `toolheads/ph_probe/ph_probe_toolhead.yaml` | Low | Current values are still placeholders — the physical measurement itself hasn't happened. The guard is now implemented: `ToolheadGeometry.geometry_validated` (default `True`, `False` for `ph_probe`) logs a warning on `set_toolhead()` and `GantryController.move_to_well()` refuses to run with a `UnvalidatedGeometryError` unless `override_unvalidated=True` is passed. Plain `move_to()`/`jog()` are unaffected — only well-targeted moves are gated. |
| Camera support | new package/device | Low | Phase 2+ feature, not part of current bench core. |
| Experiment lock does not gate motion RPCs at the backend | `devices/gantry/backend/src/rxn_bench_gantry/feature.py` | High | Confirmed in code: `move_to`/`jog`/etc. call `self._run(...)`, which only acquires `self._hw_lock` (an `asyncio.Lock` used purely for serialization) — it never checks `self._experiment_state`. A motion RPC sent directly (bypassing the UI, e.g. from another script or a raw gRPC call) while a script holds the experiment lock is **executed**, not rejected; it is merely serialized behind the same lock the script is also using. This is a real collision/safety risk, not fixed by frontend gating alone. Frontend visibility (see §5/§8) closes the *normal-operation* path but not this one. |

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
- Duplicate small utilities per device rather than extracting a shared common package. `rxn_bench_gantry/session_log.py` and `rxn_bench_ph/session_log.py` are functionally identical (byte-for-byte except one docstring word) — this is intentional, not drift to fix. Keeping each device's backend self-contained (no shared runtime dependency between otherwise-independent device packages) outweighs de-duplicating ~70 lines.
- Both drift checks (`make check-proto` in `software/backend/Makefile`; `make check-connections` in `software/frontend/Makefile`) are manual-only today — there is no CI workflow or pre-commit hook in this repo that runs either automatically. Treat them as a "run before you PR" step, not a safety net.

---

## 9. Platform Roadmap

**Long-term goal:** grow Rxn Bench from a single bench (gantry + pH) into more of an all-around laboratory control platform — many/heterogeneous devices, not just this one bench. This doesn't change anything in sections 1-8; the device-first layout, one-SiLA-server-per-device model, and mock/real hardware split already scale toward this goal without rework.

Near-term, in priority order:

1. **Workflow runner in `rxn_bench_client` — not a YAML DSL, a thin structural layer over plain Python scripts.** Experiment scripts stay arbitrary Python (loops, conditionals, numpy/pandas, adaptive logic) — that expressiveness is worth keeping, not replacing. What's missing is a lightweight decorator/context-manager per step that gives a `WorkflowRunner` enough structure to: retry/resume from the failed step instead of rerunning the whole script, know which devices a step touches before running it (so a future scheduler can avoid device contention), and record a structured per-step audit trail alongside the existing JSONL session logs. Design constraint: each step must carry an idempotency/side-effect flag, and resume-from-failed-step must default to requiring human confirmation before re-running or skipping a step — physical actions (dispensed liquid, a probe already lowered into a well) can't be rolled back the way a database transaction can. Pure Python, no new service or database; lives inside the existing client package. (MADSci itself does the analogous thing — YAML workflows plus an escape-hatch `ExperimentApplication` Python class — because pure declarative workflows aren't enough either.)
2. **Prove the pattern with a real third device** (camera is already parked as the next device in `FUTURE_IDEAS.md` §5). Bar to clear: adding it touches only a new `devices/camera/{backend,frontend}` folder — nothing in `core/` or `device_registry.py`. If that's not true, fix the abstraction before adding a 4th/5th device.

Done, as of 2026-07-01: all four gaps in the generic FDL-driven device widget (dynamic protobuf message construction, structured/list parameter support, observable-command support, typed input widgets with validation) — see `FUTURE_IDEAS.md` §1 for what was built and how it was verified.

Deferred until a concrete trigger (not speculative work — see `FUTURE_IDEAS.md` for design notes on several of these):

| Capability | Build when... |
|---|---|
| Resource/labware/inventory tracking | Juggling enough reagents/labware that a human can't track it by eye |
| Multi-bench discovery + TLS | A second physical bench/room actually exists (today's mDNS discovery is local-subnet only) |
| Autonomous experiment loop (`FUTURE_IDEAS.md` §2-4) | Unattended overnight runs are actually wanted, not just multi-instrument human-supervised control |

---

## 10. Deferred Ideas

The following ideas are intentionally moved out of the active architecture plan and into `FUTURE_IDEAS.md`:

- AI-assisted device onboarding
- runtime `OnboardingFeature`
- hot-reloadable generated device manifests
- fully metadata-driven workflow generation
- camera package/design exploration

These are interesting, but they should not block the current bench from becoming stable, installable, and testable.
