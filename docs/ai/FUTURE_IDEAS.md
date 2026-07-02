# Rxn Bench — Future Ideas

**Purpose:** Park the ambitious architecture ideas here so the active `CURRENT_STATE.md` stays focused on what is real, current, and actionable.

---

## 1. Generic FDL-Driven UI (implemented — see `core/generic_device.py` + `core/fdl_types.py`)

**This is already built and live**, not a future idea — `GenericDeviceWidget` in `software/frontend/src/rxn_bench_ui/core/generic_device.py` is the automatic fallback in `device_registry.py` for any device that doesn't match a known plugin. It does the full pipeline: fetches `SiLAService.GetFeatureDefinition(identifier)`, parses the FDL XML (commands/properties/parameter types, constraints), and renders a live collapsible panel per feature with working Get (property read) and Run (command execution) buttons over real gRPC calls.

As of 2026-07-01, the four gaps below (originally identified the same day) have all been closed:

- **Dynamic FDL→protobuf construction** (`core/fdl_types.py`, `FeatureMessageBuilder`). Real, typed protobuf messages are built at parse time from the FDL — using `google.protobuf.descriptor_pb2`/`descriptor_pool`/`message_factory` — instead of guessing value types from raw wire bytes. Wire shapes were grounded directly in `SiLAFramework.proto` and `sila.framework.data_types.*` source (installed with unitelabs-cdk), then verified against real live traffic: decoding the `Position` Structure property byte-for-byte identical to the officially compiled `motion_platform_pb2` stub, and successfully calling `PHSensor.Calibrate` (an enum-constrained String param + a Real param) against a running mock server. This also fixed a real latent bug: the old heuristic encoder zigzag-encoded `Integer` values, but the real SiLA wire type is plain `int64` — confirmed by comparing wire bytes directly against `SiLAFramework.proto`'s `Integer{int64 value=1}`.
- **Structured/List command parameters.** `_ParamInput` in `generic_device.py` renders a Structure as a nested sub-form and a List as a repeatable add/remove group of sub-forms, recursively. Verified with a full widget → dict → dynamic message → wire bytes → message → display round trip (no real device here has a Structure/List command parameter yet, so this was checked with a synthetic FDL fixture, not live backend traffic).
- **Observable commands.** `_ObservableCmdRunner` drives the real SiLA wire pattern (initiate → `CommandExecutionUUID` → poll `<Command>_Info` for status/progress → fetch `<Command>_Result`). Verified against a genuinely running server: spun up unitelabs-cdk's own built-in `ObservableCommandTest` feature (ships with the SDK for exactly this kind of testing) and drove its `Count` command end-to-end — real status transitions (`running` at 0%/50%/100% → `finishedSuccessfully`) and the correct final result.
- **Typed input widgets with validation.** Enum constraints render as a `QComboBox` (verified live against `PHSensor.Calibrate`'s `Point` parameter — dropdown populated with `mid`/`low`/`high`/`clear`); numeric range constraints render as a `QSpinBox`/`QDoubleSpinBox` with `setRange()` (Qt clamps out-of-range input at the UI level); everything else falls back to `QLineEdit`. `validate_value()` checks constraints before a Run is allowed to proceed.

Remaining open items:

- No compiled-stub support for `Date`/`Time`/`Timestamp`/`Binary`/`Any` command-parameter *input* widgets (decode/encode is fully implemented and correct for these; only the input-widget ergonomics are a plain text-box fallback rather than e.g. a date picker) — no real device here uses these types yet.
- `<Command>_Intermediate` streams (intermediate responses during an observable command, distinct from status/progress) are not implemented — `_ObservableCmdRunner` only handles the Info/Result pair.
- No confirmation/safety gate before Run beyond constraint validation (e.g. no "are you sure" for a command with no declared constraints on a real physical device).

---

## 2. AI-Assisted Device Onboarding

Long term, a new device could be described through a structured manifest and scaffolded into a backend package plus frontend plugin.

Possible flow:

```text
new device description
  -> validate manifest
  -> generate backend package skeleton
  -> generate feature/interface/server files
  -> generate frontend plugin skeleton
  -> generate connection_spec.yaml
  -> run tests in mock mode
  -> developer reviews before deployment
```

### Guardrails

- AI may generate scaffolding, but hardware behavior must be reviewed by a human.
- Motion, heating, liquid handling, pressure, voltage, and chemical-dosing commands need explicit safety checks.
- Generated code should default to mock mode until validated.
- No hot deployment to real hardware without tests passing.

---

## 3. Runtime OnboardingFeature

A future `OnboardingFeature` SiLA service could accept a validated JSON device description, write config files, and register a new device capability.

This is not a near-term requirement. It becomes useful only after:

1. config models are migrated to pydantic,
2. JSON Schema export exists,
3. device package templates are stable,
4. mock-mode testing is reliable,
5. deployment scripts are boring and repeatable.

---

## 4. Metadata-Driven Workflows

A future workflow layer could operate on capabilities instead of concrete device names.

Example:

```text
Need: measure pH in wells A1-A12
Find capabilities:
  - movable XYZ stage
  - pH probe
  - workspace with well coordinates
  - safe clearance rules
Generate workflow:
  - home if needed
  - mount pH probe if needed
  - move to well
  - read pH
  - log result
```

This should come after the current explicit script/client workflow is stable.

---

## 5. Camera Support

Camera support is deferred. When it returns, treat it as its own package/device instead of bolting it onto the gantry package.

Possible package:

```text
devices/camera/backend/src/rxn_bench_camera/
devices/camera/frontend/
```

Potential capabilities:

- image capture
- live preview
- plate/well alignment
- color measurement
- reaction monitoring

---

## 6. Things Not To Do Yet

- Do not generate production widgets from AI output.
- Do not hot-reload real hardware features without a test/review gate.
- Do not make the frontend fully generic before the handwritten gantry/pH UX is solid.
- Do not block install scripts, pH hardware wiring, or mock I2C work on the AI onboarding plan.
