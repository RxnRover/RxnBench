---
name: debug
description: Root-cause a bug in Rxn Bench by tracing execution rather than guessing at fixes. Use when the user reports an error, traceback, or unexpected behavior.
argument-hint: "[expected vs actual behavior, or paste an error]"
---

Bug report: $ARGUMENTS

Do not shotgun random fixes. Trace the execution path.

1. If the report doesn't already include them, ask for or locate: expected behavior, actual behavior, the traceback/log, and what changed recently (recent commits touching the affected files via `git log`).
2. Read the relevant code along the execution path, not just the file where the error surfaced.
3. Report:
   1. Likely root cause
   2. Evidence from the code/logs supporting it
   3. Minimal fix
   4. Safer long-term fix, if different from the minimal one
   5. A test case that would catch this regression
4. Apply the minimal fix only after confirming the root cause, unless the user asked you to just diagnose.
5. If a fix was applied: add a dated bullet to the `Unreleased` section of [CHANGELOG.md](../../../CHANGELOG.md) (prefixed with the affected area, e.g. `gantry`, `ph`), and update [docs/ai/CURRENT_STATE.md](../../../docs/ai/CURRENT_STATE.md) if the bug or its fix changes a listed gap, capability, or design decision.
