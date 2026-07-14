# Changelog

All notable changes to Rxn Bench are recorded here.

## [Unreleased]

## [0.1.1] - 2026-07-13

### Added

- frontend: `windows-latest` GitHub Actions workflow that builds the Windows desktop installer, uploads it as an artifact, and attaches it to version-tag GitHub Releases (so the `.exe` can be produced from a Linux dev machine).
- gantry: the X-gantry crossbar is now drawn in the workspace X/Z and Y/Z side views (under "show more details").
- gantry: opt-in crossbar collision check — refuses a well move or tool engagement that would drive the crossbar into a taller plate sharing the carriage's Y-row. Needs crossbar measurements in `machine.yaml` to activate.
- gantry: configurable `deck_height_mm` workspace field for the shared deck/workplate thickness, separate from each plate's own mount height and footprint. Defaults to 0, so existing workspaces are unchanged.

### Changed

- gantry: bumped the Gantry SiLA feature from v0 to v1 (`edu.iastate.ames/rxnbench/Gantry/v1`), matching pH and Camera. Frontend and backend must be deployed together.
- gantry: moving between wells of the same plate now travels at that plate's own clearance height instead of the full-deck safe height, cutting raise/lower time on multi-well scans.

### Fixed

- gantry: corrected `test_controller.py` cases that hardcoded plate dimensions instead of deriving them from the labware YAML.

## [0.1.0] - 2026-07-13

### Added

- camera: new `rxn_bench_camera` SiLA device (port 50053) that streams the latest webcam frame from a Crowsnest stream, with an adjustable capture interval and image archiving. Adds a generic SiLA `Binary` wire type and `snapshot()` / `save_snapshot()` / `set_capture_interval()` on the client.
- gantry: multi-toolhead support — several heads can be mounted at once, each confirmed once and then switched between in software; moves refuse an unmounted or uncalibrated head, and both UI slots drive their own head.
- gantry: backend enforces the experiment lock on the wire — `AcquireExperimentLock` returns a token and motion/toolhead/workspace commands take an optional `Token`; the client attaches it automatically.
- gantry: `ForceReleaseExperimentLock` — tokenless recovery for a lock stranded by a killed script, wired into the UI banner and the client.
- gantry: `GetLabware` command serves all plate-geometry YAML as the single source of truth; deck canvases and the client fetch it instead of hardcoding grids.
- gantry: non-contact Z-reference calibration — the homing dialog and toolhead wizard can hover the tip at a known reference-plate height instead of touching a surface.
- gantry: new X/Z and Y/Z workspace side views alongside the top-down view, on both the Live and Configuration tabs, showing plate heights, the deck floor, safe-travel height, and per-well engagement depth.
- ph: UART/serial driver for the Atlas EZO-pH circuit (the bench probe is wired to the Pi's UART, not I2C), selected via `RXN_BENCH_PH_TRANSPORT`, sharing one EZO command set with the I2C driver plus a serial mock.
- client: `at_well()` gains an `override_unvalidated` passthrough so scripts can use a toolhead whose geometry is still placeholder.
- frontend: PyInstaller packaging groundwork — `make dist` builds a onedir app and stages each device plugin beside the executable; plugin discovery resolves `devices/` from the executable when frozen.
- frontend: closed the four gaps in the generic FDL-driven device widget — typed protobuf messages built from the FDL, typed command inputs with validation, and observable-command support — so it drives unknown SiLA2 devices without compiled stubs.
- backend: `install.sh` (shared uv workspace for dev) and `scripts/install_service.sh` (per-package venv plus the pH `rpi` extra) so each service deploys as its own systemd unit.
- docs: `new-device` dev-agent skill for scaffolding a device, requiring reuse of existing device interfaces before creating new ones.
- docs: top-level `devices/<name>/README.md` overviews for gantry, ph_sensor, and device_template.
- testing: first test suites for the pH backend, the client (37 tests), and the frontend (15 tests), plus the gantry suite extended to 133 tests.
- repo: GitHub Actions CI running both backend suites, the frontend suite, and both drift checks on push/PR.

### Changed

- repo: renamed the top-level `software/` folder to `rxnbench/` (`rxnbench/backend`, `rxnbench/frontend`) — path references updated and generated artifacts regenerated, no architecture change.
- repo: reorganized to a device-first layout — each device is a self-contained `devices/<name>/{backend,frontend}` folder.
- gantry: safe clearance-travel height is now derived from the loaded labware geometry (new `plate_height_mm`) instead of a flat 50 mm guess.
- ph: frontend connection uses generated protobuf stubs instead of hand-rolled varint helpers (also updated in `device_template`).
- frontend: gantry workspace loader now goes through `GantryConnection` instead of opening raw gRPC channels — closing the last plugin→core-internals boundary violation.
- backend: `gen_proto.py` generalized to a per-device manifest covering gantry, pH, and the template; adding a device's stubs is one entry.
- backend: offline-bundle default target Python is now 3.13 (the reference Pi's OS ships it); override with `PYTHON_VERSION`.
- docs: refreshed `CURRENT_STATE.md` — closed gaps removed, new stable decisions recorded.

### Fixed

- frontend: Experiment Runner now runs the selected script in packaged builds instead of relaunching the app.
- deployment: SiLA server discovery on the gatewayless bench network — servers now advertise the Pi's real IP over mDNS and a boot-time multicast route lets announcements reach the wire; `install_offline.sh` auto-detects and pins the host IP.
- gantry: `move_to_well` docks at the well's actual opening and rejects a move whose engage depth exceeds the well depth, instead of overshooting.
- gantry: lock-gated commands (`LoadWorkspaceYaml`, `Jog`, `MoveTo`, …) no longer fail with "Missing field Token" — the token arg is now declared for each, with a regression test cross-checking spec args against the proto.
- gantry: toolhead calibration wizard no longer rejects auto-moves against a plate shallower than the toolhead's configured engage depth.
- gantry: one broken labware file no longer breaks `GetLabware` for every plate — bad definitions are skipped with a warning and a clear error names the file.
- gantry: `GetWorkspaceYaml` and its subscription read from the controller's workspace manager, so workspaces loaded by name or restored at boot are visible to the stream and client.
- gantry: `MoonrakerClient` HTTP calls carry timeouts, so a wedged Moonraker no longer hangs a request while holding the hardware lock.
- gantry: fixed `motion_platform.proto` drift — the generator footer was missing the experiment-lock/pause/resume/stop RPCs.
- ph: fixed the real-hardware I2C path — new `SMBusI2C` adapter (passing `SMBus(1)` directly would have crashed) plus a mock I2C emulator for tests.
- frontend: packaged builds now bundle device-plugin dependencies (`collect_submodules`, `yaml`); `make dist-check` constructs every device widget in a frozen build to catch missing imports.
- frontend: connection layer now logs stream/command failures, closes channels on disconnect, and surfaces errors in the UI.
- backend: `make start-gantry` / `-ph` / `-camera` run fully offline from an extracted bundle; also fixed `start-ph` never installing the `rpi` extra (smbus2).
- backend: `install_offline.sh` persists the vendored `uv` on `PATH` so `make start-<device>` works right after install.
- backend: `build_offline_bundle.sh` — fixed requirements-file parsing (single-line exports), aarch64 wheel downloads (`manylinux2014_aarch64` tag), and the tar step pulling in its own output.
- backend: offline `install_service.sh` now bundles its build backend (`hatchling` / `editables`) so editable installs succeed with no network.
- docs: fixed `device_template/README.md`'s onboarding checklist (stale `sila_client.py` / `_FEATURE_REGISTRY` references and old spec paths).

### Removed

- gantry: dead-code sweep — unused sensor registry, an unconsumed signal, phantom widget fields, speculative generic SiLA fragments, and a phantom 384-well plate entry.
