# Rxn Bench

Read [docs/ai/CURRENT_STATE.md](docs/ai/CURRENT_STATE.md) for the current architecture snapshot, package layout, active gaps, and stable design decisions before making changes.

Deferred/long-term ideas that should not influence current work are listed in [docs/ai/CURRENT_STATE.md](docs/ai/CURRENT_STATE.md) §10.

## Hard rules

- Frontend (`software/frontend`) and backend device servers (`devices/<name>/backend/`) run on separate machines. All frontend data must go through SiLA/gRPC — never import backend device code directly from the frontend.
- Each device plugin under `devices/<name>/frontend/` owns its own widget and connection layer. Core (`software/frontend/src/rxn_bench_ui/core/`) only handles app shell, discovery, device selection, and generic fallback UI.
- Only generate connection boilerplate (`generated_connection.py`). Never generate widgets, workflows, app/core behavior, dataclasses, or handwritten convenience methods.
