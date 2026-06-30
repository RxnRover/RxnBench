# chem-bench-client

Blocking Python client for writing experiment scripts that run on the backend machine. Wraps `sila2.SilaClient` connections to both the gantry (port 50051) and pH sensor (port 50052) servers and exposes common operations as simple method calls.

This is a library, not a server — it has no entry point and no SiLA server of its own.

---

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Both `chem-bench-gantry` and `chem-bench-ph` running (locally or on a remote Pi)

Install from the workspace root:

```bash
cd software/backend
uv sync
```

---

## Usage

### Basic experiment script

```python
from chem_bench_client import ChemBenchClient

with ChemBenchClient() as bench:
    # Load a saved workspace and toolhead
    bench.load_workspace("my_plates")
    bench.set_toolhead("ph_probe")
    bench.confirm_toolhead_mounted()

    results = {}
    for well in ["plate1/A1", "plate1/B1", "plate1/C1"]:
        bench.move_to_well(well)
        bench.engage_tool()
        results[well] = bench.read_ph()
        bench.disengage_tool()

    bench.save_and_park()

print(results)
```

### Connecting to a remote Pi

```python
with ChemBenchClient(host="192.168.1.42") as bench:
    ...
```

### Adding a new device

Pass any extra servers as `extra_servers`. The key becomes the name used in `bench.sila`:

```python
with ChemBenchClient(extra_servers={"conductivity": ("localhost", 50053)}) as bench:
    bench.sila["conductivity"].ConductivitySensor.ReadConductivity()
```

### Raw feature access

Anything not wrapped by `ChemBenchClient` is accessible directly through `bench.sila`. The `sila2` library fetches the feature definition from the server at connect time — no pre-compiled stubs needed:

```python
bench.sila["gantry"].Gantry.HomeAuto()
bench.sila["ph"].PHSensor.Calibrate(Point="mid", Value=7.0)
bench.sila["ph"].PHSensor.ReadSlope()
```

---

## API Reference

### Constructor

```python
ChemBenchClient(
    host: str = "localhost",
    gantry_port: int = 50051,
    ph_port: int = 50052,
    extra_servers: dict[str, tuple[str, int]] | None = None,
)
```

Use as a context manager (`with ChemBenchClient() as bench:`) to ensure connections are closed cleanly. Or call `bench.close()` manually.

### Workspace

| Method | Description |
|--------|-------------|
| `load_workspace(name)` | Load a named workspace from `workspace/definitions/` on the server |
| `load_workspace_yaml(content)` | Load a workspace from a raw YAML string |
| `list_workspaces()` | Returns `list[str]` of available workspace names |

### Toolhead

| Method | Description |
|--------|-------------|
| `set_toolhead(name)` | Load toolhead geometry by name |
| `confirm_toolhead_mounted()` | Mark toolhead as physically attached |
| `clear_toolhead_mounted()` | Mark toolhead as detached |
| `list_toolheads()` | Returns `list[tuple[str, str]]` of `(name, display_name)` pairs |

### Motion

| Method | Description |
|--------|-------------|
| `move_to(x, y, z)` | Absolute move in mm |
| `move_to_well(label)` | Move to a named well, e.g. `"plate1/A1"` or short form `"A1"` |
| `jog(dx, dy, dz)` | Relative move from current position |
| `engage_tool(depth?)` | Lower toolhead to engage depth (defaults to toolhead's configured z_engage) |
| `disengage_tool(depth?)` | Raise from engage depth |
| `get_position()` | Returns `(x, y, z)` tuple |
| `save_and_park()` | Park carriage and persist homing state |

### pH Sensor

| Method | Description |
|--------|-------------|
| `read_ph()` | Returns current pH as `float` (subscribes and reads one value) |

---

## How Scripts Get to the Backend

The client is a library meant to be imported in scripts that run **on the backend machine** (the Raspberry Pi, or a machine on the same network as the Pi). Options for deploying scripts:

- **`scp`** — copy the script file and run it over SSH
- **Git pull** — keep experiment scripts in a repo and pull on the backend
- **Script Runner SiLA service** — a planned future device package that accepts a script as a string and runs it server-side (Phase 2+ roadmap item)
