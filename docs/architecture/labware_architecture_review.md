# Labware Architecture Review

**Date:** June 2026  
**Scope:** `labware/` module — `WellPlate`, YAML definitions, coordinate model

---

## What Was Built

A standalone `labware/` package at the `chem_bench` root level, parallel to `io/` and `features/`. It owns the domain model for physical labware: geometry, well addressing, and coordinate conversion. The prior `io/well_plates/well_plate_config.py` was deleted; nothing imported it.

### File Layout

```
chem_bench/
  labware/
    __init__.py                           — exports WellPlate
    well_plate.py                         — data model and coordinate logic
    definitions/
      well_plate_template.yaml            — authoring guide
      96_well_standard/
        96_well_standard.yaml             — ANSI/SBS 96-well (Corning Costar 3599)
      24_well_standard/
        24_well_standard.yaml             — ANSI/SBS 24-well (Corning Costar 3526)
```

---

## Module Placement Rationale

`labware/` sits alongside `io/`, not inside it. `io/` is for hardware drivers and network clients. A well plate definition is pure geometry — it has no I/O, no hardware state, and no side effects. Placing it in `io/` would have implied a hardware dependency that does not exist. Future protocol orchestration code (workflows, SiLA features) will import from `labware/` without pulling in any hardware layer.

---

## `WellPlate` API

| Member | Type | Description |
|--------|------|-------------|
| `name` | `str` | Internal identifier, matches YAML filename |
| `display_name` | `str` | Human-readable, shown in UI |
| `layout` | `WellLayout` | Row and column counts |
| `dimensions` | `PlateDimensions` | Outer length, width, height in mm |
| `well` | `WellGeometry` | Diameter, depth, nominal volume |
| `spacing` | `WellSpacing` | Row and column center-to-center pitch in mm |
| `origin` | `WellOrigin` | A1 center offset from plate corner in mm |
| `well_count` | property | `rows × columns` |
| `row_count` / `column_count` | properties | Convenience accessors |
| `is_valid(row, col)` | method | Bounds check before coordinate math |
| `well_label(row, col)` | method | `(0, 0)` → `'A1'`, `(7, 11)` → `'H12'` |
| `parse_label(label)` | method | `'A3'` → `(0, 2)` — validated reverse lookup |
| `well_position(row, col)` | method | `(x_mm, y_mm)` relative to plate corner |
| `well_position_by_label(label)` | method | Direct label → `(x_mm, y_mm)` |
| `wells()` | method | Iterator over all `(row, col)` pairs, row-major |
| `from_yaml(path)` | classmethod | Load from an arbitrary path |
| `load(name)` | classmethod | Load from bundled `definitions/<name>/<name>.yaml` |
| `list_available()` | classmethod | Scan `definitions/` and return plate names |

---

## Coordinate Convention

```
plate corner (0, 0)
  │
  │← origin.x →│← col_spacing →│← col_spacing →│ …
  │
  ▼ origin.y
  A1 ─── A2 ─── A3 …
  │
  ▼ row_spacing
  B1 ─── B2 ─── B3 …
```

All coordinates are in mm relative to the plate's bottom-left corner (when viewed from above with A1 at top-left). The SiLA `WellPlate` feature will need to add the plate's placement offset in machine space to these values before passing them to `MotionPlatformController.move_to()`.

---

## Dataclass Choices

All sub-dataclasses (`WellLayout`, `PlateDimensions`, `WellGeometry`, `WellSpacing`, `WellOrigin`, `WellPlate`) use `frozen=True`. Rationale: a plate definition is a value object. Freezing makes it safe to share a single `WellPlate` instance across threads without copying.

---

## What Is Not Here

| Concern | Where it belongs |
|---------|-----------------|
| Plate placement in machine space | `MotionPlatformController` or the SiLA `WellPlate` feature |
| Z depth per plate type | `WellPlate` feature, derived from `PlateDimensions.height` and toolhead `z_engage` |
| Active plate registry (which plate is mounted) | SiLA `WellPlate` feature (Phase 3) |
| Pydantic validation / JSON Schema | Phase 5 — replace dataclasses with `pydantic.BaseModel` once the feature is built |
