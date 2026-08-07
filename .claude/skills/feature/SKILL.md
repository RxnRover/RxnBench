---
name: feature
description: Implement, debug, or refactor a specific outcome in Rxn Bench with a plan-then-code workflow. Use when the user gives a concrete feature/change request for this repo.
argument-hint: "[what to implement/fix/refactor]"
---

Goal: $ARGUMENTS

Follow this workflow:

1. Inspect the relevant code and summarize the current design in a couple of sentences. Check [docs/ai/CURRENT_STATE.md](../../../docs/ai/CURRENT_STATE.md) for the architecture snapshot and stable design decisions if the change touches frontend/backend boundaries, device plugins, or the generated/handwritten connection split.
2. Propose a short implementation plan (smallest coherent change; match existing architecture and style; preserve public APIs unless the goal requires otherwise). If something is ambiguous, make a reasonable assumption, state it, and proceed rather than blocking on it.
3. Make the change. Do not rewrite unrelated code.
4. Verify with tests, type checks, linting, or a reasoned manual check - whichever applies to the files touched.
5. If the change affects architecture, package/frontend layout, capabilities, gaps, or next-work priorities, update [docs/ai/CURRENT_STATE.md](../../../docs/ai/CURRENT_STATE.md) to match reality (move a gap to done, add a new gap, adjust the layout tree, etc.). Skip this step for changes with no lasting architectural relevance (typo fixes, pure refactors with no behavior/shape change).
6. Add a dated bullet to the `Unreleased` section of [CHANGELOG.md](../../../CHANGELOG.md), prefixed with the affected area (e.g. `gantry`, `ph`, `frontend`, `client`, `docs`).
7. Summarize: what changed, why, files touched, how to verify, and any risks or follow-up cleanup.
