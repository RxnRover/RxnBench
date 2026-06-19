# Future Experiment Support

**Date:** June 2026  
**Context:** How the `labware/` module enables experiment-level workflows

---

## Current State

The `labware/` module provides the geometry model. It answers "where is well B4 in plate coordinates?" It does not yet know:
- Where the plate is mounted on the bench (machine-space offset)
- Which plate is currently active
- How deep to engage the tool into a specific well

These gaps are intentional — they belong in the SiLA `WellPlate` feature (Phase 3), not in the geometry model.

---

## Path to Experiment Support

### Phase 3 — SiLA `WellPlate` Feature

The `WellPlate` feature wraps the geometry model and exposes it over gRPC:

```
SiLA WellPlate feature
  ├── ObservableProperty: active_plate  → WellPlate.name (or None)
  ├── Command: set_plate(name)          → loads WellPlate.load(name), stores placement offset
  ├── Command: move_to_well(label)      → plate.well_position_by_label(label) + placement offset
  │                                       → MotionPlatformController.move_to(x, y, z)
  └── Command: list_plates()            → WellPlate.list_available()
```

The feature owns the machine-space placement offset (where A1 is in XYZ on the bench). The labware model owns the well-to-well geometry. Each layer knows only what it needs to.

### Experiment Workflows

Once the SiLA feature exists, protocols can be expressed as sequences of well operations:

```python
# Example experiment workflow (pseudocode, not yet implemented)
plate = WellPlate.load("96_well_standard")

for row, col in plate.wells():
    label = plate.well_label(row, col)
    feature.move_to_well(label)
    ph_sensor.measure()
```

The `wells()` iterator already provides the row-major sweep order needed for this pattern. Column-major, diagonal, or custom orderings can be derived from the same `(row, col)` pairs.

### Multi-Plate Experiments

`list_available()` returns all registered plate names. A future SiLA registry feature can expose multiple mounted plates with named positions (slot A, slot B). The labware model is plate-independent — the same `WellPlate` class serves each plate; only the placement offset differs.

---

## Supported Experiment Types (Once SiLA Feature Is Built)

| Experiment Type | Required |
|-----------------|----------|
| pH screening — all wells | `wells()` iterator + `move_to_well()` |
| pH screening — column subset | `parse_label()` + `well_position_by_label()` |
| Replicate sampling (same well, multiple reads) | `parse_label()` + repeat command |
| Plate-to-plate transfer (future pipette) | `well_position()` on two plates with their offsets |
| Random-access well selection by operator | `parse_label()` validates input before motion |

---

## Dimension Verification Note

The 24-well and 96-well YAML files use ANSI/SBS reference dimensions (Corning Costar datasheets). The `origin` values (A1 center offset from the plate corner) must be physically verified against the actual plate stock on hand before any experiment that requires accurate absolute positioning. A calibration step — placing the probe tip at well A1 manually, recording the machine position, and computing the offset — will be needed before first use.

---

## Not Yet Supported

| Gap | Required for |
|-----|-------------|
| Z engage depth per well | Must be derived from toolhead `z_engage` + plate `well.depth` + placement Z |
| Partial plate fills (empty wells) | Workflow layer; labware model has no concept of occupancy |
| Tip rack geometry | Requires a `TipRack` labware class — same YAML pattern, different geometry |
| Liquid volume tracking | Workflow or LIMS layer; outside scope of geometry model |
