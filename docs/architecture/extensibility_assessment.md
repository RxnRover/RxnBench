# Extensibility Assessment

**Date:** June 2026  
**Scope:** `labware/` module — how easy is it to extend for new plate types and labware classes?

---

## Adding a New Well Plate

**Cost: zero Python changes.** Drop a YAML file in a new subdirectory:

```
labware/definitions/
  384_well_standard/
    384_well_standard.yaml    ← one new file
```

`WellPlate.list_available()` discovers it automatically. `WellPlate.load("384_well_standard")` loads it. No code changes required.

The template at `labware/definitions/well_plate_template.yaml` documents every field with units and coordinate conventions. Any plate with a rectangular well grid and uniform pitch is supported.

---

## Adding a Future Labware Class (Reservoir, Tip Rack, Deep Well)

The current `WellPlate` class hard-codes the well plate geometry model. A different labware type (single-channel reservoir, 96-position tip rack) may have different geometry rules.

The extension path:

1. Create `labware/tip_rack.py` (or `reservoir.py`) with a `TipRack` class that shares the same YAML loading pattern and `list_available()` / `load()` classmethods but has labware-specific geometry.
2. Add `labware_type: tip_rack` to its YAML files so `list_available()` (or a future `list_available(labware_type=...)`) can filter by type.
3. Export from `labware/__init__.py`.

The `WellPlate` class does not need to change. Nothing in the existing code couples to a "labware base class" that would need to be refactored. Each labware type can define its own geometry model independently.

---

## Adding New Well Geometries

`WellGeometry` currently holds `diameter`, `depth`, and `volume_ul`. Non-circular wells (square, conical bottom) would require additional fields. Since `WellGeometry` is a frozen dataclass, adding optional fields with defaults is backwards-compatible:

```python
@dataclass(frozen=True)
class WellGeometry:
    diameter: float
    depth: float
    volume_ul: float
    shape: str = "round"           # new optional field
    bottom_type: str = "flat"      # new optional field
```

Existing YAML files do not need updating — PyYAML does not fail on missing keys, and the dataclass defaults cover them. New YAML files can specify the new fields.

---

## Pydantic Migration (Phase 5)

The dataclass model is correct and sufficient for the current phase. When Phase 5 lands (pydantic models for AI-assisted onboarding), the migration is:

- Replace `@dataclass(frozen=True)` with `pydantic.BaseModel`
- Replace `WellGeometry(**data["well"])` in `from_yaml()` with `WellGeometry.model_validate(data["well"])`
- `WellPlate.model_json_schema()` then produces a JSON Schema that can be handed directly to an AI to generate a new plate definition

The method signatures (`load`, `from_yaml`, `well_position_by_label`, `wells`, `parse_label`) do not change. Callers are unaffected.

---

## Extensibility Score

| Axis | Rating | Notes |
|------|--------|-------|
| New plate types (same geometry model) | ★★★★★ | Zero code changes — YAML drop-in |
| New plate types (different pitch per axis) | ★★★★★ | Already supported — `row_spacing ≠ col_spacing` |
| Non-rectangular grids | ★★☆☆☆ | Would require a different well position model |
| New labware classes | ★★★★☆ | New Python class + YAML; no changes to `WellPlate` |
| Pydantic migration | ★★★★★ | Drop-in — same method surface |
| AI-generated plate definitions | ★★★★☆ | Template + JSON Schema (after pydantic) is the target |

---

## Limitations

- **Single-letter row designators only.** `parse_label()` accepts A–Z (26 rows max). A 1536-well plate (32 rows) would require multi-letter designators (AA, AB, …). This is a deliberate simplification; 1536-well support can be added by extending the regex and the row encoding without changing any other code.
- **Uniform pitch assumed.** `well_position()` uses constant `row_spacing` and `col_spacing`. Plates where well spacing varies by row or column (rare but exist) are not supported by this model.
- **No occupancy tracking.** The labware model is pure geometry. Whether a well is empty, full, or has been visited is a workflow concern outside this module.
