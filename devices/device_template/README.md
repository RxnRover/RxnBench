# device_template

Boilerplate for adding a new device to the rxn bench, not a real device itself. Copy this whole folder to `devices/<name>/` and follow the checklist.

- **`backend/`** — reference SiLA2 server package (`rxn_bench_template`), with `TODO`-marked stubs for the hardware `Protocol`, SiLA feature, mock, and server wiring. Start here: [backend/README.md](backend/README.md) has the full step-by-step checklist for renaming and wiring up both halves.
- **`frontend/`** — reference device plugin for the PySide6 UI: a minimal hand-built widget (no `.ui` file) plus the standard connection layer. Wire decoding uses compiled protobuf stubs in `frontend/proto/`, generated from the device's manifest entry in `software/backend/scripts/gen_proto.py` (run `make gen-proto` from `software/backend`). Delete this folder if your device doesn't need a custom widget yet — unrecognized servers fall back to the generic `GenericDeviceWidget`.

`devices/gantry/` and `devices/ph_sensor/` are the canonical real-world examples of this pattern.
