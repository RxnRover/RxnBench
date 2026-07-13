# rxn-bench-camera

SiLA2 server for a Crowsnest-managed webcam stream. Streams periodic still images as a `LatestImage` observable property and archives each capture to disk. Runs as an independent process on the device host alongside `rxn-bench-gantry`/`rxn-bench-ph`.

**Port:** 50053
**SiLA UUID:** `c100b376-f1f2-4c63-986d-448e0fdf0f57`

---

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
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

Crowsnest itself has no API - it is a process supervisor that launches a real streamer backend (ustreamer by default, sometimes mjpg-streamer) per camera defined in its own `crowsnest.conf` on the host running it (the SOVOL SV08's controller in the reference deployment). `crowsnest_camera.py` talks straight to that streamer's plain HTTP snapshot route. If a bench's `crowsnest.conf` is configured for mjpg-streamer instead of the ustreamer default, override `crowsnest_snapshot_path` in `~/.rxn_bench/machine.yaml` (e.g. `/webcam/?action=snapshot`).

**Known gap:** the exact snapshot path has not yet been verified against a live SV08/Crowsnest deployment - confirm `crowsnest_base_url`/`crowsnest_snapshot_path` on a real bench before relying on the non-mock path.

---

## Adding a Different Camera Source

Implement a class satisfying `CameraProtocol` (one method: `capture() -> bytes`) and pass it to `Camera(camera=your_instance)` in `server.py`. `CrowsnestCamera` is not referenced anywhere in the SiLA feature - only the protocol matters.

```python
# interfaces.py
class CameraProtocol(Protocol):
    def capture(self) -> bytes: ...
```
