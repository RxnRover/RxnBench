# rxn-bench-ph

SiLA2 server for the Atlas Scientific EZO-pH sensor. Reads pH over I2C, supports mid/low/high three-point calibration, and exposes a streaming `Ph` observable property. Runs as an independent process on the device host alongside `rxn-bench-gantry` (a Raspberry Pi in the reference deployment).

**Port:** 50052  
**SiLA UUID:** `c1876353-a389-430e-81b0-c8d55cd56640`

---

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Real hardware only:** a host with I2C enabled (Raspberry Pi in the reference deployment); Atlas Scientific EZO-pH circuit at I2C address `0x63`
- Access to the UniteLabs private PyPI index (see `rxnbench/backend/pyproject.toml` for the index URL)

Install dependencies from the workspace root:

```bash
cd rxnbench/backend
uv sync
```

For real hardware, install I2C support (the `rpi` extra pulls in `smbus2`; works on Raspberry Pi and other Linux SBCs with I2C):

```bash
uv sync --extra rpi
```

Enable I2C on the host if not already done (Raspberry Pi reference instructions shown; other SBCs have their own equivalent):

```bash
sudo raspi-config  # Interface Options → I2C → Enable
```

---

## Running

### Development (mock sensor)

Returns a random pH of 1 to 14 — no hardware needed:

```bash
cd rxnbench/backend
RXN_BENCH_MOCK=1 uv run rxn-bench-ph
```

### Real hardware

```bash
cd rxnbench/backend
uv run rxn-bench-ph
```

The server searches for a config file in this order:

1. `~/.rxn_bench/ph_sensor.json`
2. `configs/ph_sensor.json` (bundled default, relative to this package's own directory)

Pass an explicit config with `--config`:

```bash
uv run rxn-bench-ph --config /path/to/ph_sensor.json
```

---

## Configuration

Copy `configs/ph_sensor.json` to `~/.rxn_bench/ph_sensor.json` and edit as needed. Key fields:

| Field | Default | Description |
|-------|---------|-------------|
| `sila_server.port` | `50052` | gRPC listen port |
| `sila_server.hostname` | `0.0.0.0` | Bind address |
| `sila_server.tls` | `false` | Enable TLS (requires cert files) |

---

## SiLA Features

### `PHSensor`

**Observable Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `Ph` | `float` | Current pH reading (streams continuously) |

**Commands:**

| Command | Parameters | Description |
|---------|------------|-------------|
| `Calibrate` | `Point: string`, `Value: float` | Calibrate at a reference point. `Point` is one of `low`, `mid`, `high`. `Value` is the reference pH (e.g. `4.0`, `7.0`, `10.0`). |
| `ReadSlope` | — | Returns the calibration slope as a string (Atlas EZO `Slope?` response) |

**Calibration workflow:**

```
1. Place probe in pH 7.0 buffer → Calibrate(Point="mid", Value=7.0)
2. Place probe in pH 4.0 buffer → Calibrate(Point="low", Value=4.0)
3. Place probe in pH 10.0 buffer → Calibrate(Point="high", Value=10.0)
4. ReadSlope → verify slope is within acceptable range
```

---

## Hardware Wiring (Raspberry Pi reference)

| EZO-pH Pin | Raspberry Pi Pin |
|------------|-----------------|
| VCC | 3.3 V (Pin 1) |
| GND | GND (Pin 6) |
| SDA | GPIO 2 / SDA (Pin 3) |
| SCL | GPIO 3 / SCL (Pin 5) |

Default I2C address: `0x63`. Verify with:

```bash
i2cdetect -y 1
```

---

## Adding a Different pH Sensor

Implement a class satisfying `PHSensorProtocol` (`read()`, `calibrate()`, `slope()`, `set_temperature()`, `get_temperature()`) and pass it to `PHSensor(sensor=your_instance)` in `server.py`. The Atlas-specific driver and sensor classes are not referenced anywhere in the SiLA feature — only the protocol matters.

```python
# interfaces.py
class PHSensorProtocol(Protocol):
    def read(self) -> SensorReading: ...
    def calibrate(self, point: CalibrationPoint, value: float) -> None: ...
    def slope(self) -> str: ...
    def set_temperature(self, temp: float) -> None: ...
    def get_temperature(self) -> float: ...
```
