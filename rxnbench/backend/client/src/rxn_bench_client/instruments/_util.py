"""Small helpers shared by more than one instrument wrapper."""

from __future__ import annotations

from typing import Any


def _once(prop) -> Any:
    """Subscribe to a SiLA property, take one value, and cancel."""
    sub = prop.subscribe()
    try:
        return next(sub)
    finally:
        sub.cancel()


def _snapshot(instrument: Any, label: str) -> None:
    """Ask the owning RxnBenchClient (if any) for a snapshot after *instrument*
    just did something physical worth a picture of.

    A handful of instrument methods call this - deliberately not every
    method, since e.g. PHProbe.read() is polled every ~1s inside
    read_stable() and would flood the log. RxnBenchClient._attach() sets
    ``instrument._bench``; an instrument constructed directly (not via
    bench.connect()/bench.devices) has no ``_bench``, so this quietly does
    nothing - bench.snapshot() itself already no-ops without a camera and an
    active start_experiment() folder, so this is safe by default either way.
    """
    bench = getattr(instrument, "_bench", None)
    if bench is not None:
        bench.snapshot(label)
