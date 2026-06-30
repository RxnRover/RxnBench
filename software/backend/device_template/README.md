# device_template

Boilerplate for adding a new device to the chem bench. Copy this directory, rename everything marked `TODO`, and fill in your hardware logic. The mock runs immediately — real hardware comes later.

---

## Checklist

**1. Copy and rename the package**
```bash
cp -r device_template my_device
```

**2. Rename `chem_bench_template` → `chem_bench_mydevice` everywhere**
```bash
# In the new directory:
mv src/chem_bench_template src/chem_bench_mydevice
grep -rl "chem_bench_template\|mydevice\|MyDevice\|template" . \
  --include="*.py" --include="*.toml" --include="*.json" \
  | xargs sed -i 's/chem_bench_template/chem_bench_mydevice/g'
# Then rename classes by hand in interfaces.py, feature.py, mock_device.py, server.py
```

**3. Edit each file** — follow the `TODO` comments in order:

| File | What to change |
|------|----------------|
| `interfaces.py` | Rename `MyDeviceProtocol`; replace `read()` / `do_action()` with your hardware operations |
| `feature.py` | Rename `MyDevice`; rename `measurement` / `perform_action`; add/remove properties and commands |
| `mock_device.py` | Rename `MockMyDevice`; return realistic fixed values |
| `server.py` | Add real hardware initialisation in the `else` block |
| `_cli.py` | Set `_DEVICE_NAME` to your device's config filename stem |
| `configs/mydevice.json` | Rename file; set `port` (next available after 50052); generate a new UUID; update `name` and `description` |
| `pyproject.toml` | Rename `name`, `description`, entry point, and `packages` |

**4. Add to the uv workspace**
```toml
# software/backend/pyproject.toml
[tool.uv.workspace]
members = ["gantry", "ph_sensor", "client", "my_device"]
```

**5. Add to the frontend registry**
```python
# software/frontend/src/chem_bench_ui/sila_client.py
_FEATURE_REGISTRY = [
    ...
    FeatureDescriptor(
        name="My Device",
        identifier="edu.iastate.ames/chembench/MyDevice/v1",
        start_streams=_start_mydevice_streams,
    ),
]
```

**6. Run the mock to verify everything wires up**
```bash
cd software/backend
uv sync
CHEM_BENCH_MOCK=1 uv run chem-bench-mydevice
```

**7. Add to `ChemBenchClient`**
```python
# client/src/chem_bench_client/client.py
self.sila["mydevice"] = SilaClient(host, mydevice_port, insecure=True)

def read_mydevice(self) -> float:
    return self._subscribe_once(self.sila["mydevice"].MyDevice.Measurement)
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
my_device/
  src/chem_bench_mydevice/
    __init__.py          ← empty, leave as-is
    interfaces.py        ← Protocol (hardware contract)
    feature.py           ← SiLA feature (CDK decorators)
    mock_device.py       ← in-memory mock for dev/testing
    server.py            ← create_app() factory
    _cli.py              ← entry point
    my_driver.py         ← (optional) low-level hardware driver
  configs/
    mydevice.json        ← SiLA server identity and port
  tests/
    __init__.py
    test_mock_device.py  ← starter tests, add more
  pyproject.toml
  README.md
```

The `ph_sensor/` package is the canonical real-world example of this pattern.
