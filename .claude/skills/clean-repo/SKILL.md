---
name: clean-repo
description: Clean and simplify a repository by removing redundant code, reducing excessive comments, correcting documentation and grammar, improving organization, and preserving existing behavior.
argument-hint: "[repository location, files, folders, or components to clean]"
------------------------------------------------------------------------------

# Clean Repository

Cleanup target: `$ARGUMENTS`

Improve the requested portion of the repository without changing its intended behavior.

Do not shotgun random edits. Understand how the affected code is used before modifying, moving, consolidating, or deleting it.

## Objectives

Look for opportunities to:

* Remove dead, duplicated, obsolete, or unreachable code.
* Consolidate repeated logic where doing so clearly reduces complexity.
* Simplify unnecessarily complex implementations.
* Remove comments that merely restate the code.
* Preserve comments that explain intent, constraints, unusual behavior, or non-obvious decisions.
* Correct spelling, grammar, terminology, and unclear explanations.
* Improve names when the existing names are misleading or ambiguous.
* Organize files and modules around clear responsibilities.
* Reduce unnecessary nesting, indirection, wrappers, and abstractions.
* Remove stale documentation, examples, configuration, and compatibility code.
* Make documentation concise and consistent with the implementation.

## Safety Rules

1. Preserve externally observable behavior unless the user explicitly requests a behavior change.
2. Do not remove code merely because it appears unused in one file.
3. Before deleting or moving code, locate:

   * Imports and references.
   * Dynamic loading or registration.
   * Configuration-based references.
   * Tests and fixtures.
   * Documentation examples.
   * CLI, plugin, serialization, reflection, or framework entry points.
4. Follow the execution and dependency path, not only the file where an issue is visible.
5. Prefer small, understandable changes over broad rewrites.
6. Do not introduce a new abstraction unless it eliminates meaningful duplication or clarifies a real responsibility.
7. Do not combine unrelated cleanup with functional changes.
8. Preserve public APIs, configuration formats, file formats, and command-line behavior unless explicitly authorized to change them.
9. Do not suppress test, type-checking, or lint failures simply to make validation pass.
10. Keep project-specific terminology and style consistent with the surrounding repository.

## Workflow

### 1. Resolve the Scope

Determine whether `$ARGUMENTS` identifies:

* The entire repository.
* A directory or package.
* One or more files.
* A subsystem or feature.
* A specific cleanup concern.

If no target is supplied, inspect the repository and begin with the highest-confidence cleanup opportunities. Avoid performing a repository-wide rewrite without a clearly justified reason.

### 2. Understand the Repository

Before editing:

* Read the repository-level instructions and contributor documentation.
* Inspect relevant configuration files.
* Identify formatting, linting, type-checking, and testing commands.
* Inspect nearby modules to understand local conventions.
* Use `git status` to avoid overwriting unrelated work.
* Use `git log` and `git blame` when history would clarify why unusual code exists.

### 3. Trace Usage

For each meaningful deletion, consolidation, rename, or move:

* Search for all references.
* Trace callers and downstream consumers.
* Check tests and documentation.
* Check indirect references in configuration, registries, decorators, entry points, and string-based lookups.
* Confirm whether the code is public, internal, generated, vendored, or maintained for compatibility.

Do not classify code as redundant until its role is understood.

### 4. Build a Cleanup Inventory

Classify findings into the following categories:

#### Dead or Obsolete Code

Examples include:

* Unused functions, classes, imports, variables, and constants.
* Unreachable branches.
* Disabled code left in comments.
* Superseded implementations.
* Stale compatibility paths.
* Abandoned experimental files.

#### Duplication

Examples include:

* Repeated validation.
* Repeated conversions or formatting.
* Multiple implementations of the same operation.
* Constants or configuration duplicated across files.
* Near-identical branches that can be expressed directly.

Only consolidate duplication when the repeated code represents the same responsibility and is likely to change together.

#### Excessive Complexity

Examples include:

* Deep nesting.
* Unnecessary state.
* Pass-through wrappers.
* Overly generic helpers.
* Premature abstractions.
* Excessive inheritance.
* Fragmented control flow.
* Functions that perform several unrelated responsibilities.

Prefer direct code over clever code.

#### Comments and Documentation

Remove or rewrite:

* Comments that restate the next line.
* Commented-out code.
* Historical notes better preserved by version control.
* Stale TODOs.
* Explanations that no longer match the implementation.
* Long explanations that can be made precise and concise.

Preserve or improve:

* Rationale.
* Safety constraints.
* Hardware assumptions.
* Protocol requirements.
* Units and coordinate systems.
* Non-obvious workarounds.
* Reasons for intentionally unusual behavior.

#### Structure and Naming

Look for:

* Files with unclear or mixed responsibilities.
* Modules placed in misleading locations.
* Inconsistent naming.
* Circular dependencies.
* Public and private implementation details mixed together.
* Utilities that belong with the feature that owns them.

Avoid moving files solely for aesthetic reasons.

### 5. Prioritize Changes

Prioritize work in this order:

1. Clearly dead or incorrect material.
2. Misleading documentation and comments.
3. Low-risk simplifications.
4. Local duplication.
5. Naming improvements.
6. Structural changes.
7. Larger architectural consolidation.

Before making a structural or architectural change, verify that the benefit exceeds the migration cost and regression risk.

### 6. Apply Focused Changes

Make changes in coherent groups.

For each group:

* Keep the diff focused.
* Preserve interfaces where possible.
* Update imports and references immediately after moves or renames.
* Update nearby tests and documentation.
* Avoid unrelated formatting churn.
* Do not rewrite working code solely to match a personal preference.

When a cleanup exposes a probable bug, diagnose it separately. Confirm the root cause before applying a behavioral fix.

### 7. Validate

Run the most relevant available checks, such as:

* Existing unit and integration tests.
* Targeted tests for affected components.
* Formatting.
* Linting.
* Static type checking.
* Import or build checks.
* Documentation builds.
* CLI smoke tests.
* Repository-specific validation scripts.

After structural changes, search again for:

* Old names.
* Old paths.
* Broken imports.
* Duplicate implementations.
* Stale documentation.
* References to deleted symbols.

If the full test suite cannot be run, run the strongest targeted checks available and state what remains unverified.

## Change Documentation

When changes are applied:

1. Add a dated bullet to the `Unreleased` section of `CHANGELOG.md` when the cleanup:

   * Fixes a bug.
   * Changes behavior.
   * Changes a public interface.
   * Removes a supported capability.
   * Alters configuration or documented usage.

2. Prefix the changelog entry with the affected area, for example:

   * `gantry:`
   * `ph:`
   * `workspace:`
   * `backend:`
   * `docs:`

3. Update `.claude/CURRENT_STATE.md` when the change affects a listed:

   * Capability.
   * Known gap.
   * Limitation.
   * Design decision.
   * Architectural responsibility.

Pure formatting, spelling, and comment-only cleanup does not require a changelog entry unless the repository explicitly requires one.

## Final Report

Report:

1. **Scope inspected**
2. **Changes made**
3. **Redundant or obsolete code removed**
4. **Complexity or duplication reduced**
5. **Documentation and comment improvements**
6. **Structural or naming changes**
7. **Behavioral changes**, or explicitly state that behavior was preserved
8. **Validation performed**
9. **Remaining risks or uncertain findings**
10. **Suggested follow-up work** that was intentionally left out of the current cleanup

For important deletions or restructures, include the evidence that showed the change was safe.

Do not claim the repository is fully clean unless the entire repository was inspected and validated.
