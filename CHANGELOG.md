# Changelog

All notable changes to Rxn Bench are recorded here. Packages are currently pre-release (`0.1.0`, unversioned), so entries are dated rather than tied to semver releases until the first cut.

Format: newest entry first, one bullet per change, prefixed with the area it touches (`gantry`, `ph`, `client`, `frontend`, `docs`, etc.).

## Unreleased

- backend: add `install.sh` (shared uv workspace, for local dev) and `scripts/install_service.sh` (per-package standalone venv, plus the pH `rpi` extra on ARM) for the split gantry/pH backend, so each service can be deployed/updated as its own systemd service independently of the other (2026-07-01).
- docs: fix `device_template/README.md`'s onboarding checklist — step 5 referenced a `sila_client.py`/`_FEATURE_REGISTRY` file removed in the June frontend refactor; replaced with the actual auto-discovery mechanism (`devices.all_devices()`) and the previously-missing frontend widget/connection-generation steps. Also fixed stale `connections/specs/`-era paths in the gantry and pH `connection_spec.yaml` header comments (2026-07-01).
- repo: reorganize to a device-first layout — each device is now a self-contained `devices/<name>/{backend,frontend}` folder (gantry, ph_sensor, device_template) instead of being split across `software/backend/<name>` and `software/frontend/.../devices/<name>`. `software/backend/pyproject.toml`'s uv workspace members now point at `../../devices/<name>/backend`; the Makefile and `scripts/install_service.sh` paths were updated to match. `rxn_bench_ui/devices/__init__.py` now dynamically loads each `devices/<name>/frontend/` from the repo root (via `importlib.util.spec_from_file_location`) instead of scanning a local subfolder. Added `devices/device_template/frontend/` — the template previously only covered the backend half. No behavior change for the SiLA/gRPC machine-separation boundary or the generated/handwritten connection split (2026-07-01).
- docs: add a top-level `devices/<name>/README.md` overview for gantry, ph_sensor, and device_template (what the device is, backend vs. frontend halves, links to the detailed backend README). Fixed stale content in the existing backend READMEs left over from the device-first move: broken `../pyproject.toml`/`gantry/tests/`-style relative paths, and gantry's systemd note which said "needs updating for the two-server architecture" even though that's now done (2026-07-01).
- _(add entries above this line as changes land)_
