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
make gen-proto        # writes devices/<name>/capability/frontend/src/*/proto/*.proto (+ _pb2.py)
make check-proto      # CI drift check
```

## Production / offline deployment

Install each server as its own systemd service, or build an offline bundle for a
Pi with no internet. See [../../docs/usage.md](../../docs/usage.md) and
[../../docs/deployment.md](../../docs/deployment.md).

## Updating the Pi over SSH

Quick note for pushing a code change to the reference bench Pi. The Pi lives on
the isolated, gatewayless bench network, so it has **no internet** — you can't
`git pull` on it. Get the new source over from your dev machine, then restart.

```bash
# 1. From your dev machine (plugged into the bench switch): sync the repo over.
#    scp/USB works too; rsync just skips unchanged files.
rsync -av --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  ./ <user>@192.168.50.1:~/Automated_Chem_Bench/

# 2. SSH in and restart the service(s) you changed.
ssh <user>@192.168.50.1
sudo systemctl restart rxn-bench-gantry   # or rxn-bench-ph / rxn-bench-camera

# 3. Confirm it came back up.
sudo systemctl status rxn-bench-gantry
journalctl -u rxn-bench-gantry -f
```

The services are **editable** installs (`uv pip install -e`), so a plain
`systemctl restart` picks up Python source changes — no venv rebuild needed.

Rebuild the venv only when it's more than source, by re-running the installer
for that one device (rebuilds its `.venv`, restarts only its service):

```bash
cd ~/Automated_Chem_Bench/rxnbench/backend
./scripts/install_service.sh gantry
```

Do that when: dependencies changed (`pyproject.toml`), a driver setup step
changed, or you added a new device. Changes to `~/.rxn_bench/<device>.json`
(e.g. the advertise IP) just need a `systemctl restart`.

Service ⇄ device names: `rxn-bench-gantry`, `rxn-bench-ph`, `rxn-bench-camera`.
The Pi's bench address `192.168.50.1` is static and never changes. See
[../../docs/deployment.md](../../docs/deployment.md) for the full ops story.
