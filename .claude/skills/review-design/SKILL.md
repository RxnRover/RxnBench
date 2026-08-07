---
name: review-design
description: Senior-architect-style design review of Rxn Bench code or docs - separation of generated vs handwritten code, type safety, concurrency, testability, module boundaries. Use for architecture/design review requests, not routine PR diff review (use /code-review for that).
argument-hint: "[area or files to review, and the concern]"
---

Review target: $ARGUMENTS

Review as a senior software architect, focused on:

1. Separation of generated vs human-maintained code (see [docs/ai/CURRENT_STATE.md](../../../docs/ai/CURRENT_STATE.md) section 3 for the generator boundary this project already committed to).
2. Type safety
3. Async/concurrency risks (gRPC streams, Qt signal/slot threading)
4. Testability
5. Long-term maintainability
6. Whether folder/module boundaries are clean (frontend `core/` vs `devices/<name>/`, backend package-per-device split)

Constraints:
- Do not suggest a total rewrite unless the current design is fundamentally broken.
- Prefer incremental changes.
- Distinguish: must fix now / should fix soon / nice later.
- Cross-check against [docs/ai/CURRENT_STATE.md](../../../docs/ai/CURRENT_STATE.md) section 8 (Stable Design Decisions) - don't recommend against a decision already made there without flagging that explicitly.

Return:
1. Verdict
2. Top risks found, ranked
3. Recommended structure, with concrete file/folder examples if it changes
4. Migration steps, if any
5. Anti-patterns to avoid going forward
