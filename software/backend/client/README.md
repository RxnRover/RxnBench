# rxn-bench-client

Blocking Python client for writing experiment scripts that run on the backend machine. Wraps `sila2.SilaClient` connections to instrument servers (gantry on port 50051, pH sensor on port 50052) and exposes common operations as simple method calls through per-instrument strategy classes.

This is a library, not a server — it has no entry point and no SiLA server of its own.

---

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- `rxn-bench-gantry` and/or `rxn-bench-ph` running (locally, mocked, or on a remote device host) — see [../../../docs/usage.md](../../../docs/usage.md)

Install from the workspace root:

```bash
cd software/backend
uv sync
```

---

## Usage

### Basic experiment script

```python
from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

with RxnBenchClient() as bench:
    # Server names are discovered automatically on the local network (mDNS).
    bench.connect("gantry", Gantry, server="Gantry")
    bench.connect("ph", PHProbe, server="pH")

    bench.set_log_output("results/scan.csv")
    bench.gantry.load_workspace_yaml()
    bench.gantry.mount_toolhead("ph_probe")

    for well in bench.gantry.get_workspace_wells("plate1"):
        with bench.at_well(well, stabilize=3):
            bench.log(ph=bench.ph.read())  # well is saved to the log automatically

    bench.gantry.save_and_park()
```

### Connecting explicitly (e.g. a remote device host)

Skip mDNS discovery by passing `host`/`port` instead of `server`:

```python
with RxnBenchClient() as bench:
    bench.connect("gantry", Gantry, host="192.168.1.42", port=50051)
    bench.connect("ph", PHProbe, host="192.168.1.42", port=50052)
```

### Adding a new device

Any instrument class that accepts a `SilaClient` in its constructor can be connected the same way — see `instruments.py` for the `Gantry`/`PHProbe` pattern to follow:

```python
bench.connect("conductivity", ConductivitySensor, server="rxn-bench-conductivity")
bench.conductivity.read()
```

---

## API Reference

### `RxnBenchClient`

```python
RxnBenchClient(host: str = "localhost")
```

Use as a context manager (`with RxnBenchClient() as bench:`) to ensure connections and the experiment lock are released cleanly. Or call `bench.close()` manually.

| Method | Description |
|--------|-------------|
| `connect(name, cls, *, server=None, host=None, port=None)` | Connect to a SiLA server and expose it as `bench.<name>`. Pass `server` for mDNS discovery, or `host`/`port` explicitly. |
| `at_well(well, stabilize=0.0)` | Context manager: move to well, engage tool, wait `stabilize` seconds, run body, disengage. Requires a connected `gantry`. |
| `check_pause_stop()` | Raise `ExperimentStopped` if the UI stop button was pressed; blocks while paused. Called automatically by `at_well()`. |
| `set_log_output(path, columns=None)` | Open a CSV file for `bench.log()`. |
| `log(**kwargs)` | Append one row (with timestamp, and current well if inside `at_well()`) to the log file. |
| `close()` | Release the experiment lock, close the log file, and close all instrument connections. |

### `Gantry` (`bench.connect("gantry", Gantry, ...)`)

| Method | Description |
|--------|-------------|
| `load_workspace(name)` / `load_workspace_yaml(content=None)` | Load a workspace by name or raw YAML (`None` uses whatever is active on the server). |
| `list_workspaces()` | Returns `list[str]` of available workspace names. |
| `get_workspace_wells(plate_id=None, plate_grids=None)` | Returns `list[str]` of `"plate_id/well"` labels in the active workspace. |
| `set_toolhead(name)` / `confirm_toolhead_mounted()` / `mount_toolhead(name)` | Load toolhead geometry and mark it mounted (`mount_toolhead` does both). |
| `clear_toolhead_mounted()` / `list_toolheads()` | Mark detached / list `(name, display_name)` pairs. |
| `move_to(x, y, z)` / `move_to_well(label)` / `jog(dx, dy, dz)` | Motion commands. |
| `engage_tool(depth=None)` / `disengage_tool(depth=None)` | Defaults to the toolhead's configured `z_engage`. |
| `get_position()` | Returns `(x, y, z)` tuple. |
| `save_and_park()` | Park carriage and persist homing state. |

### `PHProbe` (`bench.connect("ph", PHProbe, ...)`)

| Method | Description |
|--------|-------------|
| `read()` | Single pH reading. |
| `read_avg(n=5, interval=1.0)` | Average of `n` readings, `interval` seconds apart. |
| `read_stable(tolerance=0.05, timeout=60.0, interval=2.0)` | Read until two consecutive readings agree within `tolerance`. |
| `wait_for(*, above=None, below=None, timeout=300.0, interval=5.0)` | Block until pH crosses a threshold. |
| `calibrate(point, value)` | Calibrate at `"low"`/`"mid"`/`"high"` with a known buffer `value`. |

---

## How Scripts Get to the Backend

The client is a library meant to be imported in scripts that run **on the backend machine** (a Raspberry Pi in the reference deployment, or a machine on the same network as the backend host). Options for deploying scripts:

- **`scp`** — copy the script file and run it over SSH
- **Git pull** — keep experiment scripts in a repo and pull on the backend
- **Script Runner SiLA service** — a planned future device package that accepts a script as a string and runs it server-side (Phase 2+ roadmap item)
