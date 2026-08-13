# rxn-bench-camera

SiLA2 server for the camera capability: streams periodic still images as a `LatestImage` observable property and archives each capture to disk. Hardware-agnostic - actual image capture happens through whichever driver is registered (reference driver: `rxn-bench-crowsnest-camera-driver`, a Crowsnest-managed webcam stream - see [../../driver/README.md](../../driver/README.md)). Runs as an independent process on the device host alongside `rxn-bench-gantry`/`rxn-bench-ph`.

**Port:** 50053
**SiLA UUID:** `c100b376-f1f2-4c63-986d-448e0fdf0f57`

---

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) - install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Real hardware only:** a webcam already streaming through [Crowsnest](https://github.com/mainsail-crew/crowsnest) (or a compatible ustreamer/mjpg-streamer HTTP endpoint) on the same network
- Access to the UniteLabs private PyPI index (see `rxnbench/backend/pyproject.toml` for the index URL)

Install dependencies from the workspace root:

```bash
cd rxnbench/backend
uv sync
```

---

## Running

### Development (mock camera)

Returns a fixed placeholder image - no hardware or network needed:

```bash
cd rxnbench/backend
RXN_BENCH_MOCK=1 uv run rxn-bench-camera
```

### Real hardware

```bash
cd rxnbench/backend
uv run rxn-bench-camera
```

The server searches for a config file in this order:

1. `~/.rxn_bench/camera.json`
2. `configs/camera.json` (bundled default, relative to this package's own directory)

Pass an explicit config with `--config`:

```bash
uv run rxn-bench-camera --config /path/to/camera.json
```

---

## Configuration

`configs/camera.json` holds the SiLA server identity/port (same shape as every other device's config - see `sila_server.port`/`hostname`/`tls`).

Crowsnest connection settings live separately, in `~/.rxn_bench/machine.yaml` (shared with the gantry package's `moonraker_fallback_host` - both describe the same physical bench machine):

| Field | Default | Description |
|-------|---------|-------------|
| `crowsnest_base_url` | `http://sv08.local:8080` | Host:port Crowsnest's streamer is listening on |
| `crowsnest_snapshot_path` | `/snapshot` | HTTP path returning one JPEG frame (ustreamer's default; use e.g. `/webcam/?action=snapshot` for mjpg-streamer) |
| `capture_interval_s` | `30.0` | Seconds between captures - also runtime-adjustable via the `SetCaptureInterval` command |

Shorter intervals give more responsive live viewing at the cost of faster growth of `logs/images/` (each capture is archived - see below).

---

## SiLA Features

### `Camera`

**Observable Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `LatestImage` | `bytes` (SiLA Binary) | Most recently captured frame, JPEG-encoded. Streams a new value every `capture_interval_s`. |

**Commands:**

| Command | Parameters | Description |
|---------|------------|-------------|
| `SetCaptureInterval` | `Seconds: float` | Change how often `LatestImage` captures (and archives) a new frame. Must be positive. |

---

## Logging

Every capture is logged twice:

- `logs/<timestamp>.jsonl` - one line per capture (filename + size), auto-pruned after 30 days. Same append-only JSONL pattern as every other device's `session_log.py`.
- `logs/images/camera_<timestamp>.jpg` - the actual frame, auto-pruned after 7 days (`image_log.py`) since binary frames are far heavier than a log line. Tune `capture_interval_s` or `ImageLog`'s `max_days` if this doesn't fit the host's storage budget.

---

## Crowsnest Wiring

Crowsnest itself has no API - it is a process supervisor that launches a real streamer backend (ustreamer by default, sometimes mjpg-streamer) per camera defined in its own `crowsnest.conf` on the host running it (the SOVOL SV08's controller in the reference deployment). The driver package's `crowsnest_camera.py` talks straight to that streamer's plain HTTP snapshot route. If a bench's `crowsnest.conf` is configured for mjpg-streamer instead of the ustreamer default, override `crowsnest_snapshot_path` in `~/.rxn_bench/machine.yaml` (e.g. `/webcam/?action=snapshot`).

**Verified 2026-08-13 on the reference bench:** the defaults above did *not* work as-is. `sv08.local` doesn't resolve (mDNS doesn't cross the Pi/SV08 subnet boundary, same cause as `moonraker_fallback_host` needing a pinned IP), and Crowsnest/ustreamer isn't reachable on port 8080 at all on this SV08 - Fluidd's own nginx proxies the webcam through port 80 at `/webcam/snapshot` instead. This bench's `~/.rxn_bench/machine.yaml` sets `crowsnest_base_url: "http://192.168.10.2"` and `crowsnest_snapshot_path: "/webcam/snapshot"` accordingly. If your SV08/Fluidd setup differs, `curl` a few candidate ports/paths from the Pi before trusting the defaults - don't assume ustreamer's raw port is exposed.

---

## Adding a Different Camera Source

`server.py` never imports a concrete driver - it asks an entry-point registry for whichever name `RXN_BENCH_CAMERA_DRIVER` names (default: `crowsnest`). A different camera source plugs in with **no changes to this package**:

1. In a new package, implement a class/factory satisfying `CameraProtocol` (one method: `capture() -> bytes`):

   ```python
   # interfaces.py
   class CameraProtocol(Protocol):
       def capture(self) -> bytes: ...
   ```

2. Register a factory function under the `rxn_bench.camera_drivers` entry-point group in that package's `pyproject.toml` - see [`../../driver/backend/pyproject.toml`](../../driver/backend/pyproject.toml) for the exact shape.
3. Select it with `RXN_BENCH_CAMERA_DRIVER=<your-entry-point-name>`.
