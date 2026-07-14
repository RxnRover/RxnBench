# Rxn Bench Server

The device side of the Rxn Bench. Each device is an independent SiLA2 server:

| Server            | Command            | Port  |
| ----------------- | ------------------ | ----- |
| Gantry            | `rxn-bench-gantry` | 50051 |
| pH sensor         | `rxn-bench-ph`     | 50052 |
| Camera            | `rxn-bench-camera` | 50053 |
| <device>          | `rxn-bench-<device>| 5005x |

Also hosts [`client/`](client/README.md) - the `rxn-bench-client` Python package
experiment scripts use to drive the bench. Run all commands below from this directory

## Requirements

- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
```

On the device host (a Raspberry Pi in the reference deployment), `./install.sh`
wraps this, installs `uv` if missing, and adds the pH sensor's I2C deps on ARM.

## Start the servers

### Mock hardware (no physical bench needed)

```bash
make start-mock                       # all three, in the background
# or one at a time:
RXN_BENCH_MOCK=1 uv run rxn-bench-gantry
```

Stop the background mocks with `pkill -f rxn-bench-gantry` (and `-ph`, `-camera`).

### Real hardware

```bash
make start-gantry     # or: uv run rxn-bench-gantry
make start-ph         # or: uv run rxn-bench-ph
make start-camera     # or: uv run rxn-bench-camera
```

Each server reads `~/.rxn_bench/<name>.json` if present, else the bundled
`<package>/configs/<name>.json`. Override with `--config /path/to/file.json`.

## Test

```bash
make test             # all devices + client (or: make test-gantry / test-ph / test-camera / test-client)
```

## Regenerate proto stubs

After changing a device's SiLA feature/command manifest:

```bash
make gen-proto        # writes devices/<name>/frontend/proto/*.proto (+ _pb2.py)
make check-proto      # CI drift check
```

## Production / offline deployment

Install each server as its own systemd service, or build an offline bundle for a
Pi with no internet. See [../../docs/usage.md](../../docs/usage.md) and
[../../docs/deployment.md](../../docs/deployment.md).
