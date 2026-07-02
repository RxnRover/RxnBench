# Rxn Bench — Future Ideas

**Purpose:** Park the ambitious architecture ideas here so the active `CURRENT_STATE.md` stays focused on what is real, current, and actionable.

---

## 1. Generic FDL-Driven UI

SiLA feature definitions can expose commands, properties, parameters, and data types through FDL. A future frontend could use this to build a generic device panel for unknown or newly added SiLA features.

Potential pipeline:

```text
SiLAService.GetFeatureDefinition(identifier)
  -> FDL XML
  -> parse commands/properties/data types
  -> generate a generic Qt panel
  -> allow basic command execution and observable-property display
```

This should remain a fallback or inspection tool, not a replacement for high-quality handwritten widgets such as the gantry and pH panels.

### Open questions

- How much of the SiLA FDL type system should be mapped to Qt widgets?
- How should units, ranges, enums, and validation errors be presented?
- Should generated panels be read-only by default for safety?
- How should long-running observable commands be visualized?

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
