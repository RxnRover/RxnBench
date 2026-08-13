"""Resumable step tracking for experiment scripts."""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
from typing import Any, Callable, Generator, Iterable, TypeVar

T = TypeVar("T")


class StepNeedsConfirmation(RuntimeError):
    """Raised by :meth:`WorkflowRunner.step` when resuming an unsafe step.

    The prior attempt at this step_id either failed or crashed mid-step
    (status stuck at "running") and the step isn't declared ``idempotent`` -
    re-running it might repeat a physical side effect (a dispense, a descent
    into a well). Pass ``confirm_retry=True`` once a human has checked it's
    safe to redo.
    """


class WorkflowRunner:
    """Tracks step status in an append-only JSONL manifest for resume/audit.

    Args:
        manifest_path: Where to persist step status. A relative path is
            resolved against ``RXN_BENCH_RESULTS_DIR`` when set (matching
            ``RxnBenchClient.set_log_output``), otherwise the current working
            directory. Unlike ``set_log_output``, an existing file at this
            path is *reused*, not renamed aside - that's how resume works:
            point a second run at the same manifest to pick up where the
            first left off.
        restart: Discard any prior manifest at this path and start clean,
            instead of resuming from it. The file itself is still reused (so
            a second ``restart=True`` run overwrites, not appends-forever),
            just its history isn't loaded.
    """

    def __init__(self, manifest_path: str | pathlib.Path, *, restart: bool = False) -> None:
        path = pathlib.Path(manifest_path)
        if not path.is_absolute():
            base = os.environ.get("RXN_BENCH_RESULTS_DIR")
            path = (pathlib.Path(base) if base else pathlib.Path.cwd()) / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        if restart:
            self._entries: dict[str, dict[str, Any]] = {}
            self._file = open(path, "w", encoding="utf-8")  # truncate - old history discarded
        else:
            self._entries = _load_manifest(path)
            self._file = open(path, "a", encoding="utf-8")

    def is_done(self, step_id: str) -> bool:
        """True if *step_id* completed successfully on a prior run."""
        entry = self._entries.get(step_id)
        return entry is not None and entry["status"] == "done"

    def remaining(
        self,
        items: Iterable[T],
        key: Callable[[T], str],
    ) -> Generator[T, None, None]:
        """Yield only the items of *items* not already marked done.

        *key* maps an item to the step_id that will be passed to
        :meth:`step` for it. Skipping happens here, before the loop body
        runs at all - a plain ``with`` block can't skip its own body, so
        resumable "don't even touch this well again" behavior has to filter
        the loop, not the context manager.
        """
        for item in items:
            if not self.is_done(key(item)):
                yield item

    @contextlib.contextmanager
    def step(
        self,
        step_id: str,
        *,
        devices: Iterable[str] = (),
        idempotent: bool = False,
        confirm_retry: bool = False,
    ) -> Generator[None, None, None]:
        """Record *step_id* as running, then done or failed, around one step body.

        Args:
            step_id:       Stable identifier for this step across runs (e.g.
                            ``f"well:{well}"``). Re-running a script must pass
                            the same id for the same logical step.
            devices:        Names of devices this step touches, for the audit
                            trail (and future contention-aware scheduling) -
                            purely informational today.
            idempotent:     True if re-running this step causes no incorrect
                            side effect (e.g. it only reads). Skips the
                            confirm_retry requirement after a failure.
            confirm_retry:  Explicitly allow re-running a step whose last
                            attempt failed or crashed mid-step. Get this from
                            a human, not a hardcoded True.

        Raises:
            StepNeedsConfirmation: The prior attempt at this step_id didn't
                reach "done", and neither idempotent nor confirm_retry was
                set.
        """
        prior = self._entries.get(step_id)
        if (
            prior is not None
            and prior["status"] != "done"
            and not idempotent
            and not confirm_retry
        ):
            raise StepNeedsConfirmation(
                f"Step {step_id!r} previously {prior['status']} "
                f"({prior.get('error', 'no partial result recorded')!r}). "
                "Confirm no unsafe physical side effect was left behind, then "
                "retry with confirm_retry=True (or idempotent=True if this "
                "step is safe to redo unconditionally)."
            )
        self._write(step_id, status="running", devices=list(devices), idempotent=idempotent)
        try:
            yield
        except Exception as e:
            self._write(step_id, status="failed", error=repr(e))
            raise
        else:
            self._write(step_id, status="done")

    def _write(self, step_id: str, **fields: Any) -> None:
        row = {
            "step_id": step_id,
            "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds"),
            **fields,
        }
        self._entries[step_id] = row
        json.dump(row, self._file)
        self._file.write("\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "WorkflowRunner":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def pending_step(manifest_path: str | pathlib.Path) -> dict[str, Any] | None:
    """Return the first step in *manifest_path* that never reached "done".

    None if the manifest doesn't exist, or every step it recorded completed.
    A read-only, no-side-effect check - doesn't open the manifest for
    writing or hold it open, so it's safe to call before deciding whether to
    construct a :class:`WorkflowRunner` at all (e.g. to offer a resume-or-
    restart choice before a script even starts).
    """
    entries = _load_manifest(pathlib.Path(manifest_path))
    for entry in entries.values():
        if entry.get("status") != "done":
            return entry
    return None


def _load_manifest(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Replay a manifest file into ``{step_id: latest status row}``."""
    entries: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            entries[row["step_id"]] = row
    return entries
