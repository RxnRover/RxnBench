# Usage

Commands to install dependencies and start the backend servers and frontend UI.

## Requirements

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) - `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Install

```bash
cd software/backend && uv sync
cd software/frontend && uv sync
```

On the Raspberry Pi, `software/backend/install.sh` wraps the above, installs `uv` if missing, and pulls in the pH sensor's I2C dependencies automatically when run on ARM hardware. This gives you the shared dev workspace used by `make start-mock`/`make test`/etc.

For production, install each server as a systemd service. This gives gantry and pH their own standalone venv (`devices/gantry/backend/.venv`, `devices/ph_sensor/backend/.venv`), separate from the shared dev workspace venv above, so either service can be updated and restarted independently:

```bash
#in the software/backend directory
scripts/install_service.sh gantry
scripts/install_service.sh ph
```

Re-running `scripts/install_service.sh <gantry|ph>` later refreshes just that service's venv and restarts it, without touching the other service.

## Start the backend servers

The gantry (`rxn-bench-gantry`, port 50051) and pH sensor (`rxn-bench-ph`, port 50052) run as independent SiLA2 servers, normally on the Raspberry Pi.

### Mock hardware (no Pi, no SV08, no sensor needed)

Starts both servers in the background with simulated hardware:

```bash
#in the software/backend directory
make start-mock
```

Or start one at a time:

```bash
#in the software/backend directory
RXN_BENCH_MOCK=1 uv run rxn-bench-gantry
RXN_BENCH_MOCK=1 uv run rxn-bench-ph
```

### Real hardware

```bash
#in the software/backend directory
make start-gantry   # or: uv run rxn-bench-gantry
make start-ph        # or: uv run rxn-bench-ph
```

Each server looks for a config file at `~/.rxn_bench/<name>.json`, falling back to the bundled `<package>/configs/<name>.json`. Pass `--config /path/to/file.json` to override.

## Start the frontend UI

```bash
#in the software/frontend directory
uv run rxn-bench-ui
```

The UI discovers the gantry and pH servers automatically via mDNS on the local network (works with either the mock or real servers above).

## Run an experiment script

Experiment scripts use `rxn-bench-client` and connect to whichever servers are running - see [software/backend/client/README.md](../software/backend/client/README.md) and [software/backend/client/tutorial_script.py](../software/backend/client/tutorial_script.py):

```bash
#in the software/backend directory
uv run --package rxn-bench-client python client/tutorial_script.py
```

## Stop the mock servers

`make start-mock` launches both servers in the background; stop them with:

```bash
pkill -f rxn-bench-gantry
pkill -f rxn-bench-ph
```
