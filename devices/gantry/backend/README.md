# rxn-bench-gantry

SiLA2 server for the Sovol SV08 gantry motion platform. Drives the XYZ carriage via Moonraker (Klipper REST API), manages toolhead config, workspace/well-plate layout, and homing state. Runs as an independent process on the Raspberry Pi.

**Port:** 50051  
**SiLA UUID:** `a9a1052f-64e0-4108-bb32-361c2facb4fb`

---

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Moonraker running on the SV08 at port 7125 (auto-discovered via mDNS or IPv6 link-local)
- Access to the UniteLabs private PyPI index (see `software/backend/pyproject.toml` for the index URL)

Install dependencies from the workspace root:

```bash
cd software/backend
uv sync
```

---

## Running

### Development (mock hardware)

No SV08 or Moonraker needed — all motion is simulated in memory:

```bash
cd software/backend
RXN_BENCH_MOCK=1 uv run rxn-bench-gantry
```

### Real hardware

```bash
cd software/backend
uv run rxn-bench-gantry
```

The server searches for a config file in this order:

1. `~/.rxn_bench/gantry.json`
2. `configs/gantry.json` (bundled default, relative to this package's own directory)

Pass an explicit config with `--config`:

```bash
uv run rxn-bench-gantry --config /path/to/gantry.json
```

### As a systemd service

From `software/backend`, run `scripts/install_service.sh gantry`. This builds a standalone venv at `devices/gantry/backend/.venv` (separate from the shared dev workspace venv) and registers `rxn-bench-gantry.service`, so it can be updated/restarted independently of the pH service.

---

## Configuration

Copy `configs/gantry.json` to `~/.rxn_bench/gantry.json` and edit as needed. Key fields:

| Field | Default | Description |
|-------|---------|-------------|
| `sila_server.port` | `50051` | gRPC listen port |
| `sila_server.hostname` | `0.0.0.0` | Bind address |
| `sila_server.tls` | `false` | Enable TLS (requires cert files) |

Machine axis limits live in `~/.rxn_bench/machine.yaml` (auto-created with defaults on first run). Homing calibration is persisted to `~/.rxn_bench/homing_state.json` on `SaveAndPark` and auto-restored on startup.

---

## SiLA Features

### `Gantry`

**Observable Properties** (streaming, subscribe once — updates pushed on change):

| Property | Type | Description |
|----------|------|-------------|
| `Position` | `{X, Y, Z: float}` | Current carriage position in mm |
| `State` | `string` | Klipper printer state (`ready`, `printing`, etc.) |
| `ToolheadInfo` | `{active, name, footprint_x, footprint_y, tip_offset_z, z_engage, toolhead_mounted: ...}` | Active toolhead geometry and mount state |
| `HasSavedState` | `bool` | Whether a valid homing state exists on disk |

**Motion Commands:**

| Command | Parameters | Description |
|---------|------------|-------------|
| `MoveTo` | `X, Y, Z: float` | Absolute move with safe Z clearance travel |
| `Jog` | `Dx, Dy, Dz: float` | Relative move from current position |
| `MoveToWell` | `Label: string` | Move to a named well in the active workspace (e.g. `plate1/A1`) |
| `EngageTool` | `Depth: float` | Lower toolhead to engage depth |
| `DisengageTool` | `Depth: float` | Raise toolhead from engage depth |
| `SaveAndPark` | — | Park carriage and persist homing state to disk |
| `GetLimits` | — | Returns `"x_min\|x_max\|y_min\|y_max\|z_min\|z_max"` |

**Homing Commands:**

| Command | Description |
|---------|-------------|
| `HomeAuto` | Automatic homing using endstops (requires no toolhead, or a toolhead that supports auto homing) |
| `StartManualHoming` | Begin manual homing sequence |
| `ConfirmXMin` / `ConfirmXMax` | Mark current position as X axis limit during manual homing |
| `ConfirmYMin` / `ConfirmYMax` | Mark current position as Y axis limit |
| `ConfirmZReference` | Mark current Z as reference point |
| `FinishHoming` | Complete manual homing and persist calibration |
| `SetZ` | `Z: float` — manually set current Z value |

**Toolhead Commands:**

| Command | Parameters | Description |
|---------|------------|-------------|
| `SetToolhead` | `Name: string` | Load toolhead geometry by name |
| `ClearToolhead` | — | Remove active toolhead |
| `ConfirmToolheadMounted` | — | Mark toolhead as physically attached |
| `ClearToolheadMounted` | — | Mark toolhead as detached |
| `ListToolheads` | — | Returns newline-delimited `name \| display_name` pairs |

**Workspace Commands:**

| Command | Parameters | Description |
|---------|------------|-------------|
| `SetWorkspace` | `Name: string` | Load a workspace by name from `workspace/definitions/` |
| `LoadWorkspaceYaml` | `Content: string` | Load workspace from a raw YAML string |
| `ListWorkspaces` | — | Returns newline-delimited available workspace names |

---

## Adding a Toolhead

Drop a new folder under `src/rxn_bench_gantry/toolheads/` following the template:

```
toolheads/
  my_probe/
    my_probe_toolhead.yaml
```

Use `src/rxn_bench_gantry/toolheads/toolhead_config_template.yaml` as the schema. The toolhead appears in `ListToolheads` on next server start — no Python changes needed.

## Adding a Well Plate

Drop a new YAML under `src/rxn_bench_gantry/labware/` following the existing `96_well_standard.yaml` schema. It appears in workspace configs immediately — no Python changes needed.

---

## Tests

```bash
cd software/backend
make test-gantry
# or directly:
PYTHONPATH="" uv run --package rxn-bench-gantry pytest ../../devices/gantry/backend/tests/ -v
```

`PYTHONPATH=""` strips the ROS2 system path to prevent plugin conflicts.

## Proto Generation (frontend stubs only)

The `Position` and `ToolheadInfo` dataclasses in `feature.py` are the source of truth for the frontend proto:

```bash
cd software/backend
make gen-proto     # regenerate + recompile stubs
make check-proto   # verify stubs match source (run in CI)
```
