# device_template

Boilerplate for adding a new device to the rxn bench. Each device is a self-contained `devices/<name>/{backend,frontend}` folder (see `docs/ai/CURRENT_STATE.md`). Copy this directory, rename everything marked `TODO`, and fill in your hardware logic. The mock runs immediately — real hardware comes later.

---

## Checklist

**1. Copy and rename the device folder**
```bash
# from the repo root
cp -r devices/device_template devices/my_device
```

**2. Rename `rxn_bench_template` → `rxn_bench_mydevice` in the backend half**
```bash
# In devices/my_device/backend/:
mv src/rxn_bench_template src/rxn_bench_mydevice
grep -rl "rxn_bench_template\|mydevice\|MyDevice\|template" . \
  --include="*.py" --include="*.toml" --include="*.json" \
  | xargs sed -i 's/rxn_bench_template/rxn_bench_mydevice/g'
# Then rename classes by hand in interfaces.py, feature.py, mock_device.py, server.py
```

**3. Edit each backend file** — follow the `TODO` comments in order:

| File | What to change |
|------|----------------|
| `interfaces.py` | Rename `MyDeviceProtocol`; replace `read()` / `do_action()` with your hardware operations |
| `feature.py` | Rename `MyDevice`; rename `measurement` / `perform_action`; add/remove properties and commands |
| `mock_device.py` | Rename `MockMyDevice`; return realistic fixed values |
| `server.py` | Add real hardware initialisation in the `else` block |
| `_cli.py` | Set `_DEVICE_NAME` to your device's config filename stem |
| `configs/mydevice.json` | Rename file; set `port` (next available after 50052); generate a new UUID; update `name` and `description` |
| `pyproject.toml` | Rename `name`, `description`, entry point, and `packages` |

**4. Add the backend to the uv workspace**
```toml
# rxnbench/backend/pyproject.toml
[tool.uv.workspace]
members = [
    "../../devices/gantry/backend",
    "../../devices/ph_sensor/backend",
    "../../devices/my_device/backend",
    "client",
]
```

**5. Edit the frontend device plugin**

There is no registry file to edit — `rxn_bench_ui.devices.all_devices()` auto-discovers every `devices/<name>/frontend/` folder at the repo root. `devices/my_device/frontend/` already exists (copied in step 1) with the same shape as `devices/gantry/frontend/` and `devices/ph_sensor/frontend/`:

```text
devices/my_device/frontend/
  __init__.py             ← exports FEATURE_FRAGMENTS + create_widget()
  connection_spec.yaml    ← manifest: streams/commands this feature exposes
  generated_connection.py ← generated boilerplate, do not hand-edit
  connection.py           ← handwritten subclass: decode handlers, convenience methods
  widget.py               ← handwritten Qt widget
```

- `__init__.py` follows the same contract as [devices/gantry/frontend/`__init__.py`](../../gantry/frontend/__init__.py): a `FEATURE_FRAGMENTS: list[str]` matched against advertised SiLA feature identifiers, and `create_widget(server, theme) -> QWidget`. Rename the fragments and widget class.
- Add your device to `_DEVICES` in `rxnbench/backend/scripts/gen_proto.py` and run `make gen-proto` (from `rxnbench/backend`) to generate the protobuf stubs into `frontend/proto/`. Then update `connection_spec.yaml` (see [devices/gantry/frontend/connection_spec.yaml](../../gantry/frontend/connection_spec.yaml) or [devices/ph_sensor/frontend/connection_spec.yaml](../../ph_sensor/frontend/connection_spec.yaml)) and regenerate the boilerplate from `rxnbench/frontend/`:

  ```bash
  python scripts/gen_connections.py \
      ../../devices/my_device/frontend/connection_spec.yaml \
      --out ../../devices/my_device/frontend/generated_connection.py
  ```

- `connection.py` subclasses the generated base and adds decode handlers/convenience methods by hand. `widget.py` is fully handwritten — never generated (see `CLAUDE.md`).
- If you don't need a custom widget yet, you can delete `devices/my_device/frontend/` entirely: unrecognized servers fall back to the generic `GenericDeviceWidget`.

**6. Run the mock to verify everything wires up**
```bash
cd rxnbench/backend
uv sync
RXN_BENCH_MOCK=1 uv run rxn-bench-mydevice
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

## Generating a new UUID

```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

Each device must have a unique UUID in its config. Never reuse the template UUID.

---

## File structure reference

```
devices/my_device/
  backend/
    src/rxn_bench_mydevice/
      __init__.py          ← empty, leave as-is
      interfaces.py        ← Protocol (hardware contract)
      feature.py           ← SiLA feature (CDK decorators)
      mock_device.py       ← in-memory mock for dev/testing
      server.py            ← create_app() factory
      _cli.py               ← entry point
      my_driver.py          ← (optional) low-level hardware driver
    configs/
      mydevice.json        ← SiLA server identity and port
    tests/
      __init__.py
      test_mock_device.py  ← starter tests, add more
    pyproject.toml
    README.md
  frontend/
    __init__.py             ← FEATURE_FRAGMENTS + create_widget()
    connection_spec.yaml    ← manifest for gen_connections.py
    generated_connection.py ← generated, do not hand-edit
    connection.py           ← handwritten decode handlers/convenience methods
    widget.py                ← handwritten Qt widget
```

The `ph_sensor/` package is the canonical real-world example of this pattern.
