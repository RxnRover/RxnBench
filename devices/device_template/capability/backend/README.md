# device_template

Boilerplate for adding a new device to the rxn bench. Each device is a self-contained `devices/<name>/` folder, split into a `capability/{backend,frontend}` (the SiLA feature + widget - hardware-agnostic) and, if it has real vendor hardware, a `driver/` (see `docs/ai/CURRENT_STATE.md` §1 "Capability + driver split"). Copy this directory, rename everything marked `TODO`, and fill in your logic. The mock runs immediately - real hardware comes later.

This template only has a `capability/` - its mock is a generic stub, not real hardware, so there's nothing to split into a driver yet. If your device does have real hardware, see `devices/ph_sensor/` for the fullest worked example (driver package, wire-protocol mocks, hardware CAD, entry-point registration).

---

## Checklist

**1. Copy and rename the device folder**
```bash
# from the repo root
cp -r devices/device_template devices/my_device
```

**2. Rename `rxn_bench_template` -> `rxn_bench_mydevice` in the capability backend**
```bash
# In devices/my_device/capability/backend/:
mv src/rxn_bench_template src/rxn_bench_mydevice
grep -rl "rxn_bench_template\|mydevice\|MyDevice\|template" . \
  --include="*.py" --include="*.toml" --include="*.json" \
  | xargs sed -i 's/rxn_bench_template/rxn_bench_mydevice/g'
# Then rename classes by hand in interfaces.py, feature.py, mock_device.py, server.py
```

**3. Edit each capability backend file** - follow the `TODO` comments in order:

| File | What to change |
|------|----------------|
| `interfaces.py` | Rename `MyDeviceProtocol`; replace `read()` / `do_action()` with your hardware operations |
| `feature.py` | Rename `MyDevice`; rename `measurement` / `perform_action`; add/remove properties and commands |
| `mock_device.py` | Rename `MockMyDevice`; return realistic fixed values |
| `server.py` | If you have real hardware, add a driver package (see "Adding a driver" below) instead of initialising it inline |
| `_cli.py` | Set `_DEVICE_NAME` to your device's config filename stem |
| `configs/mydevice.json` | Rename file; set `port` (next available after 50054); generate a new UUID; update `name` and `description` |
| `pyproject.toml` | Rename `name`, `description`, entry point, and `packages` |

**4. Add the capability backend to the uv workspace**
```toml
# rxnbench/backend/pyproject.toml
[tool.uv.workspace]
members = [
    "../../devices/gantry/capability/backend",
    "../../devices/ph_sensor/capability/backend",
    "../../devices/my_device/capability/backend",
    "client",
]
```

**5. Wire up the frontend device plugin**

`devices/my_device/capability/frontend/` already exists (copied in step 1), with the same shape as `devices/gantry/capability/frontend/` and `devices/ph_sensor/capability/frontend/`:

```text
devices/my_device/capability/frontend/
  pyproject.toml                              <- declares the "rxn_bench.devices" entry point
  src/rxn_bench_mydevice_frontend/
    __init__.py             <- exports FEATURE_FRAGMENTS + create_widget()
    connection_spec.yaml    <- manifest: streams/commands this feature exposes
    generated_connection.py <- generated boilerplate, do not hand-edit
    connection.py           <- handwritten subclass: decode handlers, convenience methods
    widget.py                <- handwritten Qt widget
```

It's discovered via a Python entry point, not a config file to edit by hand:

1. Rename the package (`src/rxn_bench_device_template_frontend/` -> `src/rxn_bench_mydevice_frontend/`) and update `pyproject.toml`'s `name`, `packages`, and `[project.entry-points."rxn_bench.devices"]` line (`device_template = "..."` -> `my_device = "rxn_bench_mydevice_frontend"`).
2. Add it to `rxnbench/frontend/pyproject.toml`, mirroring the existing devices - one line in `dependencies` (`"rxn-bench-my-device-frontend"`) and one in `[tool.uv.sources]` (`rxn-bench-my-device-frontend = { path = "../../devices/my_device/capability/frontend", editable = true }`). `uv sync` from `rxnbench/frontend/` then installs it and `rxn_bench_ui.devices.all_devices()` picks it up automatically - no core code to edit.
3. `__init__.py` follows the same contract: a `FEATURE_FRAGMENTS: list[str]` matched against advertised SiLA feature identifiers, and `create_widget(server, theme) -> QWidget`. Rename the fragments and widget class.
4. Add your device to `_DEVICES` in `rxnbench/backend/scripts/gen_proto.py` and run `make gen-proto` (from `rxnbench/backend`) to generate the protobuf stubs. Then update `connection_spec.yaml` and regenerate the connection boilerplate from `rxnbench/frontend/`:

   ```bash
   make gen-connections   # regenerates every device's generated_connection.py from its connection_spec.yaml
   ```

5. `connection.py` subclasses the generated base and adds decode handlers/convenience methods by hand. `widget.py` is fully handwritten - never generated (see `CLAUDE.md`).
6. If you don't need a custom widget yet, you can delete `devices/my_device/capability/frontend/` entirely: unrecognized servers fall back to the generic `GenericDeviceWidget`. (There's also a zero-setup drop-in path with no `pyproject.toml`/entry point at all - a flat `devices/my_device/frontend/__init__.py` - still supported as a fallback for quick experiments, but the entry-points shape above is what ships for real.)

**6. Run the mock to verify everything wires up**
```bash
cd rxnbench/backend
make install   # uv sync + aggregate_toolheads.py
RXN_BENCH_MOCK=1 uv run --package rxn-bench-mydevice rxn-bench-mydevice
```

**7. Add an instrument class to `rxn-bench-client`**
```python
# rxnbench/backend/client/src/rxn_bench_client/instruments.py
class MyDevice:
    def __init__(self, sila: SilaClient) -> None:
        self._d = sila

    def read(self) -> float:
        return _once(self._d.MyDevice.Measurement)
```
Export it from `rxnbench/backend/client/src/rxn_bench_client/__init__.py`, then use it like the built-in instruments:
```python
bench.connect("mydevice", MyDevice, server="rxn-bench-mydevice")
bench.mydevice.read()
```

---

## Adding a driver (only if you have real hardware)

Once `mock_device.py` isn't enough and you're wiring up an actual instrument, don't put the vendor-specific code in `capability/backend/` - give it its own `devices/my_device/driver/backend/` package instead, so the capability stays hardware-agnostic and reusable:

1. Implement a class/factory satisfying your `interfaces.py` Protocol in the new driver package.
2. Register a factory function under a new `rxn_bench.mydevice_drivers` entry-point group in the driver package's `pyproject.toml`.
3. In `capability/backend/src/rxn_bench_mydevice/server.py`, load it via `importlib.metadata.entry_points(group="rxn_bench.mydevice_drivers")` instead of importing it directly - see `devices/ph_sensor/capability/backend/src/rxn_bench_ph/server.py` for the exact pattern (it also shows the `RXN_BENCH_MOCK=1` short-circuit staying capability-side).
4. Add the driver package to the uv workspace's `[tool.uv.sources]` as a plain editable path dependency of the capability package - **not** a separate `[tool.uv.workspace] members` entry (a real uv limitation with reciprocal `{workspace = true}` sources - see `docs/ai/CURRENT_STATE.md` §1).

`devices/ph_sensor/` is the fullest worked example: two transports, wire-protocol mocks, hardware CAD (`driver/hardware_models/`), and a gantry toolhead config (`driver/toolhead/`).

---

## Generating a new UUID

```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

Each device must have a unique UUID in its config. Never reuse the template UUID.

---

## File structure reference

```
devices/my_device/
  capability/
    backend/
      src/rxn_bench_mydevice/
        __init__.py          <- empty, leave as-is
        interfaces.py        <- Protocol (hardware contract)
        feature.py           <- SiLA feature (CDK decorators)
        mock_device.py       <- in-memory mock for dev/testing
        server.py            <- create_app() factory; loads a driver via entry points if you have one
        _cli.py               <- entry point
      configs/
        mydevice.json        <- SiLA server identity and port
      tests/
        __init__.py
        test_mock_device.py  <- starter tests, add more
      pyproject.toml
      README.md
    frontend/
      pyproject.toml           <- declares the "rxn_bench.devices" entry point
      src/rxn_bench_mydevice_frontend/
        __init__.py             <- FEATURE_FRAGMENTS + create_widget()
        connection_spec.yaml    <- manifest for gen_connections.py
        generated_connection.py <- generated, do not hand-edit
        connection.py           <- handwritten decode handlers/convenience methods
        widget.py                <- handwritten Qt widget
  driver/                       <- only if you have real hardware - see "Adding a driver" above
    backend/
      src/rxn_bench_<vendor>_driver/
      pyproject.toml            <- declares a "rxn_bench.mydevice_drivers" entry point
    hardware_models/            <- CAD for this device's hardware, if any
    toolhead/                   <- gantry toolhead config, if this device mounts on the gantry
```

`devices/ph_sensor/` is the canonical real-world example of this pattern, including the driver split.
