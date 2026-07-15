# Rxn Bench (UI)

Desktop control app for the Rxn Bench. It discovers the backend SiLA2 device
servers (gantry, pH, camera) over mDNS on the local network and drives them over
gRPC. Device widgets are drop-in plugins loaded from `devices/*/frontend/`.

Runs on a separate machine from the backend - all data goes over SiLA/gRPC.

## Requirements

- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- For building a distribution: the `package` dependency group (PyInstaller), pulled in with `uv sync --group package`

## Run in development

```bash
uv sync
uv run rxn-bench-ui
```

The UI finds any running servers automatically (mock or real - see
[../backend/README.md](../backend/README.md) to start them).

## Build a distribution

PyInstaller can't cross-compile, so build on the OS you're targeting.

### Linux

```bash
make dist          # onedir build -> dist/Rxn Bench/
make dist-check    # optional: constructs every device widget in the frozen build to catch missing deps
"./dist/Rxn Bench/Rxn Bench"
```

`make dist` also stages each `devices/<name>/frontend/` next to the executable,
so the packaged app keeps the drop-in plugin model - no rebuild needed to add a
device later.

### Windows installer

```bash
make installer     # -> dist-installer/Rxn-Bench-Setup-<version>.exe
```

Requires [Inno Setup](https://jrsoftware.org/isinfo.php)'s `ISCC.exe` on `PATH`
(Windows only). The installer is per-user by default (no admin needed) and
version is read from `pyproject.toml`.

Easiest way to produce the Windows `.exe` from a Linux dev machine: push a `v*`
tag (or run the **Windows installer** workflow manually). GitHub Actions
(`.github/workflows/windows-installer.yml`) builds it on a `windows-latest`
runner and attaches the installer to the tagged GitHub Release.

## Test

```bash
make test          # headless generator/error/geometry tests
```
