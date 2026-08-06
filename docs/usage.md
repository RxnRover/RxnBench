# Usage

Commands to install dependencies and start the backend servers and frontend UI.

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) - `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Install

```bash
cd rxnbench/backend && uv sync
cd rxnbench/frontend && uv sync
```

On the device host (a Raspberry Pi in the reference deployment), `rxnbench/backend/install.sh` wraps the above, installs `uv` if missing, and pulls in the pH sensor's I2C dependencies automatically when run on ARM hardware. This gives you the shared dev workspace used by `make start-mock`/`make test`/etc.

For production, install each server as a systemd service. This gives each device its own standalone venv (`devices/gantry/capability/backend/.venv`, `devices/ph_sensor/capability/backend/.venv`, `devices/camera/capability/backend/.venv` - the driver package installs into the same venv automatically, as a dependency of the capability), separate from the shared dev workspace venv above, so any service can be updated and restarted independently:

```bash
#in the rxnbench/backend directory
scripts/install_service.sh gantry
scripts/install_service.sh ph
scripts/install_service.sh camera
```

Re-running `scripts/install_service.sh <gantry|ph|camera>` later refreshes just that service's venv and restarts it, without touching the others.

For a fresh device host with no internet access (Raspberry Pi in the reference deployment), see [deployment.md](deployment.md) - it covers building an offline install bundle and bringing up every service with a single `install_offline.sh` command.

## Start the backend servers

The gantry (`rxn-bench-gantry`, port 50051), pH sensor (`rxn-bench-ph`, port 50052), and camera (`rxn-bench-camera`, port 50053) run as independent SiLA2 servers on whatever machine hosts the backend (a Raspberry Pi in the reference deployment).

### Mock hardware (no device host, no gantry hardware, no sensor or camera needed)

Starts every server in the background with simulated hardware:

```bash
#in the rxnbench/backend directory
make start-mock
```

Or start one at a time:

```bash
#in the rxnbench/backend directory
RXN_BENCH_MOCK=1 uv run rxn-bench-gantry
RXN_BENCH_MOCK=1 uv run rxn-bench-ph
RXN_BENCH_MOCK=1 uv run rxn-bench-camera
```

### Real hardware

```bash
#in the rxnbench/backend directory
make start-gantry   # or: uv run rxn-bench-gantry
make start-ph        # or: uv run rxn-bench-ph
make start-camera    # or: uv run rxn-bench-camera
```

Running from inside an extracted offline bundle (see [deployment.md](deployment.md))
instead of the shared dev workspace? `make start-<device>` detects the bundle's
`wheelhouse/` automatically and installs+runs fully offline, without needing
`scripts/install_service.sh` or network access - `uv run rxn-bench-<device>` on its own
does *not* do this (it always resyncs the full project lockfile, dev deps included,
against PyPI), so use `make start-<device>` rather than the raw `uv run` form in that case.

Each server looks for a config file at `~/.rxn_bench/<name>.json`, falling back to the bundled `<package>/configs/<name>.json`. Pass `--config /path/to/file.json` to override.

## Start the frontend UI

```bash
#in the rxnbench/frontend directory
uv run rxn-bench-ui
```

The UI discovers the gantry, pH, and camera servers automatically via mDNS on the local network (works with either the mock or real servers above).

## Run an experiment script

Experiment scripts use `rxn-bench-client` and connect to whichever servers are running - see [rxnbench/backend/client/README.md](../rxnbench/backend/client/README.md) and [rxnbench/backend/client/tutorial_script.py](../rxnbench/backend/client/tutorial_script.py):

```bash
#in the rxnbench/backend directory
uv run --package rxn-bench-client python client/tutorial_script.py
```

## Stop the mock servers

`make start-mock` launches every server in the background; stop them with:

```bash
pkill -f rxn-bench-gantry
pkill -f rxn-bench-ph
pkill -f rxn-bench-camera
```
