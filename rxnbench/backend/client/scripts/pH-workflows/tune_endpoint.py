# Offline tuner for the pH endpoint detector.
#
# Replays the SHIPPING stability detector (_StabilityMonitor - the same class
# PHProbe.read_stable() uses) over recorded pH traces across a grid of
# thresholds, and reports for each config how fast it stops, how close the
# accepted value lands to the trace's equilibrium, and how often it stops
# prematurely or times out. Because it drives the real detector rather than a
# copy, the numbers stay honest as the algorithm evolves.
#
# The reference "truth" for each trace is the average of its final seconds, so
# only traces that actually flatten by the end are used (the rest are excluded
# and reported - a high exclude rate is itself a finding about the hardware).
#
# Usage:
#   python tune_endpoint.py                 # built-in synthetic traces (no hardware)
#   python tune_endpoint.py path/to/traces  # recorded <well>.csv traces (t, ph columns)
#                                            # as produced by record_ph_traces.py

from __future__ import annotations

import csv
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from rxn_bench_client.instruments import _StabilityMonitor

Sample = tuple[float, float]  # (elapsed_seconds, pH)
Trace = list[Sample]


# --- Configs to compare ------------------------------------------------------
# Tune the WHOLE detector, not the slope in isolation: window, min_settle,
# max_range, and stable_checks all interact with max_drift (e.g. a wider window
# integrates the slope over more time, tightening its effective bound). This
# default grid sweeps the drift threshold with the others held at read_stable()'s
# current defaults - edit it to co-vary whichever axes you care about.


@dataclass(frozen=True)
class EndpointConfig:
    """One point in the tuning grid - mirrors read_stable()'s keyword args."""

    name: str
    window: int = 10
    min_settle: float = 5.0
    max_drift: float = 0.002
    max_range: float = 0.03
    stable_checks: int = 3
    timeout: float = 60.0


CONFIGS = [
    EndpointConfig("drift=0.0100", max_drift=0.0100),
    EndpointConfig("drift=0.0050", max_drift=0.0050),
    EndpointConfig("drift=0.0020", max_drift=0.0020),  # read_stable's current default
    EndpointConfig("drift=0.0010", max_drift=0.0010),
    EndpointConfig("drift=0.0005", max_drift=0.0005),
]


# --- Scientific requirements -------------------------------------------------
# The optimization target: the fastest config whose accepted values stay close
# enough to equilibrium, without stopping early or timing out too often.
REFERENCE_SECONDS = 10.0  # tail averaged for the equilibrium reference value
TAIL_FLAT_PTP = 0.02      # a trace whose tail isn't this flat never settled -> excluded
PREMATURE_TOL = 0.05      # a stop landing outside this of equilibrium = stopped too early
REQUIRE_P95 = 0.02        # 95% of stops must land within this of equilibrium
REQUIRE_P99 = 0.05        # 99% must land within this
REQUIRE_TIMEOUT_RATE = 0.10
REQUIRE_PREMATURE_RATE = 0.05


@dataclass
class ReplayResult:
    stopped: bool
    time_to_stop: float  # nan if it never settled within the timeout
    accepted: float      # nan if it never settled


def replay(trace: Trace, cfg: EndpointConfig) -> ReplayResult:
    """Feed *trace* to a fresh detector configured by *cfg*, as read_stable would."""
    mon = _StabilityMonitor(
        window=cfg.window,
        min_settle=cfg.min_settle,
        max_drift=cfg.max_drift,
        max_range=cfg.max_range,
        stable_checks=cfg.stable_checks,
    )
    t0 = trace[0][0]
    for t, ph in trace:
        elapsed = t - t0
        if mon.update(elapsed, ph):
            return ReplayResult(True, elapsed, mon.mean())
        if elapsed >= cfg.timeout:
            break
    return ReplayResult(False, math.nan, math.nan)


def reference_value(trace: Trace, seconds: float) -> float:
    """Equilibrium reference = mean pH over the final *seconds* of the trace."""
    cutoff = trace[-1][0] - seconds
    tail = [ph for t, ph in trace if t >= cutoff and math.isfinite(ph)]
    return statistics.fmean(tail) if tail else math.nan


def tail_is_flat(trace: Trace, seconds: float, max_ptp: float) -> bool:
    """True if the trace's final *seconds* span no more than *max_ptp* pH."""
    cutoff = trace[-1][0] - seconds
    tail = [ph for t, ph in trace if t >= cutoff and math.isfinite(ph)]
    return len(tail) >= 2 and (max(tail) - min(tail)) <= max_ptp


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (pct in [0, 1]); nan for an empty list."""
    if not values:
        return math.nan
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


def evaluate(corpus: list[tuple[Trace, float]], cfg: EndpointConfig) -> dict:
    """Aggregate replay stats for *cfg* across the (trace, reference) *corpus*."""
    times: list[float] = []
    abs_errors: list[float] = []
    premature = timeouts = 0
    for trace, ref in corpus:
        r = replay(trace, cfg)
        if not r.stopped:
            timeouts += 1
            continue
        err = abs(r.accepted - ref)
        times.append(r.time_to_stop)
        abs_errors.append(err)
        if err > PREMATURE_TOL:
            premature += 1
    n = len(corpus)
    return {
        "cfg": cfg,
        "median_time": statistics.median(times) if times else math.nan,
        "p95_err": _percentile(abs_errors, 0.95),
        "p99_err": _percentile(abs_errors, 0.99),
        "premature_rate": premature / n,
        "timeout_rate": timeouts / n,
    }


def _meets(row: dict) -> bool:
    """True if a config clears every scientific requirement (nan comparisons fail)."""
    return (
        row["p95_err"] <= REQUIRE_P95
        and row["p99_err"] <= REQUIRE_P99
        and row["premature_rate"] <= REQUIRE_PREMATURE_RATE
        and row["timeout_rate"] <= REQUIRE_TIMEOUT_RATE
    )


def _fmt(x: float, spec: str) -> str:
    return "  -  " if math.isnan(x) else format(x, spec)


def print_report(rows: list[dict]) -> None:
    header = f"{'config':<14}{'median_t':>9}{'p95_err':>9}{'p99_err':>9}{'premat':>8}{'timeout':>9}{'meets':>7}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['cfg'].name:<14}"
            f"{_fmt(row['median_time'], '.1f'):>7} s"
            f"{_fmt(row['p95_err'], '.3f'):>9}"
            f"{_fmt(row['p99_err'], '.3f'):>9}"
            f"{_fmt(row['premature_rate'] * 100, '.0f'):>7}%"
            f"{_fmt(row['timeout_rate'] * 100, '.0f'):>8}%"
            f"{'yes' if _meets(row) else 'no':>7}"
        )

    # Optimization target: the fastest config that clears every requirement.
    passing = [r for r in rows if _meets(r)]
    print()
    if passing:
        best = min(passing, key=lambda r: r["median_time"])
        print(
            f"Recommended: {best['cfg'].name} - fastest config meeting "
            f"p95<={REQUIRE_P95}, p99<={REQUIRE_P99} pH "
            f"(median {best['median_time']:.1f} s)."
        )
    else:
        print(
            "No config met all requirements. Loosen the targets, record more "
            "settled traces, or investigate probe/sample settling."
        )


# --- Trace sources -----------------------------------------------------------


def load_traces(dir_path: str) -> list[Trace]:
    """Load ``<well>.csv`` traces (t, ph columns) from *dir_path*."""
    traces: list[Trace] = []
    for path in sorted(Path(dir_path).glob("*.csv")):
        trace: Trace = []
        with open(path, newline="", encoding="utf-8") as f:
            for record in csv.DictReader(f):
                try:
                    trace.append((float(record["t"]), float(record["ph"])))
                except (KeyError, ValueError, TypeError):
                    # TypeError: a truncated row leaves a column as None (float(None)).
                    continue
        if trace:
            traces.append(trace)
    return traces


def synthetic_traces() -> list[Trace]:
    """A small stand-in corpus so the tuner runs before real traces exist.

    Each trace is a first-order exponential settle to a target pH plus Gaussian
    noise; ``never_settles`` keeps a slow residual creep so it fails the tail
    flatness filter and is excluded, exercising that guard.
    """
    import random

    rng = random.Random(0)
    # (name, tau_s, noise_sd, start_pH, target_pH, residual_drift_per_s)
    specs = [
        ("buffer7_a", 3.0, 0.002, 7.30, 7.00, 0.0),
        ("buffer7_b", 3.5, 0.003, 6.60, 7.00, 0.0),
        ("buffer4_a", 3.0, 0.002, 4.25, 4.00, 0.0),
        ("buffer4_b", 3.5, 0.003, 3.68, 4.00, 0.0),
        ("noisy", 3.0, 0.012, 6.60, 7.00, 0.0),          # excluded: tail too noisy
        ("never_settles", 25.0, 0.004, 6.20, 7.00, 0.003),  # excluded: residual creep
    ]
    traces: list[Trace] = []
    for _name, tau, sd, start, target, drift in specs:
        trace = [
            (
                float(i),
                target + (start - target) * math.exp(-i / tau) + drift * i + rng.gauss(0, sd),
            )
            for i in range(121)  # 0..120 s at 1 Hz
        ]
        traces.append(trace)
    return traces


def main() -> None:
    if len(sys.argv) > 1:
        raw = load_traces(sys.argv[1])
        source = sys.argv[1]
    else:
        raw = synthetic_traces()
        source = "built-in synthetic traces (pass a directory to use recorded ones)"

    # Keep only traces that actually settled - their tail is the reference truth.
    corpus: list[tuple[Trace, float]] = []
    excluded = 0
    for trace in raw:
        if tail_is_flat(trace, REFERENCE_SECONDS, TAIL_FLAT_PTP):
            corpus.append((trace, reference_value(trace, REFERENCE_SECONDS)))
        else:
            excluded += 1

    print(f"Source: {source}")
    print(
        f"Traces: {len(raw)} total, {len(corpus)} settled, "
        f"{excluded} excluded (tail not flat within {TAIL_FLAT_PTP} pH)\n"
    )
    if not corpus:
        print("No settled traces to evaluate.")
        return

    print_report([evaluate(corpus, cfg) for cfg in CONFIGS])


if __name__ == "__main__":
    main()
