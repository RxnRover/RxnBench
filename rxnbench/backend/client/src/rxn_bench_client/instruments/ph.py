"""pH probe instrument wrapper."""

from __future__ import annotations

import math
import time
from collections import deque

from sila2.client import SilaClient

from ._util import _once, _snapshot


def _regression_slope(times: list[float], values: list[float]) -> float:
    """Least-squares slope of *values* vs *times*

    Returns 0.0 when the slope is undefined - fewer than two points, or all
    timestamps equal (duplicate/degenerate sampling) - so callers can lean on
    the peak-to-peak range instead of dividing by a zero time span.
    """
    n = len(times)
    if n < 2:
        return 0.0
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    denom = sum((t - mean_t) ** 2 for t in times)
    if denom == 0.0:
        return 0.0
    num = sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values))
    return num / denom


class _StabilityMonitor:
    """Sliding-window endpoint detector for a settling signal.

    A window is only ever evaluated after it is full *and* at least *min_settle*
    seconds have elapsed, so a probe can't be declared stable before it has had
    time to settle. Any window that fails, or a non-finite reading, resets the
    consecutive counter - a single glitch or excursion restarts the streak.
    """

    def __init__(
        self,
        *,
        window: int,
        min_settle: float,
        max_drift: float,
        max_range: float,
        stable_checks: int,
    ) -> None:
        if window < 2:
            raise ValueError("window must be at least 2")
        if stable_checks < 1:
            raise ValueError("stable_checks must be at least 1")
        self._min_settle = min_settle
        self._max_drift = max_drift
        self._max_range = max_range
        self._stable_checks = stable_checks
        self._times: deque[float] = deque(maxlen=window)
        self._values: deque[float] = deque(maxlen=window)
        self._window = window
        self._consecutive = 0

    def update(self, elapsed: float, value: float) -> bool:
        """Feed one sample; return True once the signal is considered stable.

        Args:
            elapsed: Seconds since the measurement started (the regression's
                time axis). Non-finite values are ignored.
            value:   Latest reading; NaN/inf readings break the stable streak.
        """
        if not math.isfinite(value):
            self._consecutive = 0
            return False
        self._times.append(elapsed)
        self._values.append(value)
        if len(self._values) < self._window or elapsed < self._min_settle:
            return False
        if abs(self.slope()) <= self._max_drift and self.ptp() <= self._max_range:
            self._consecutive += 1
        else:
            self._consecutive = 0
        return self._consecutive >= self._stable_checks

    def slope(self) -> float:
        """Regression drift (value/second) across the current window."""
        return _regression_slope(list(self._times), list(self._values))

    def ptp(self) -> float:
        """Peak-to-peak range (value) across the current window."""
        return max(self._values) - min(self._values) if self._values else 0.0

    def mean(self) -> float:
        """Mean value of the current window - the settled measurement."""
        return sum(self._values) / len(self._values)


class PHProbe:
    """pH probe instrument. Attach via bench.connect("ph", PHProbe, server=...).

    Examples::

        bench.connect("ph", PHProbe, server="rxn-bench-ph")

        ph = bench.ph.read()                           # single reading
        ph = bench.ph.read_avg(n=5)                    # average over 5 readings
        ph = bench.ph.read_stable()                    # wait for probe to settle
        ph = bench.ph.wait_for(above=7.0, timeout=120) # block until threshold
    """

    def __init__(self, sila: SilaClient) -> None:
        """
        Args:
            sila: Connected SilaClient pointed at the pH sensor server.
        """
        self._p = sila

    def read(self) -> float:
        """Single pH reading."""
        return _once(self._p.PHSensor.Ph)

    def read_avg(self, n: int = 5, interval: float = 1.0) -> float:
        """Average of *n* readings taken *interval* seconds apart."""
        readings = [self.read()]
        for _ in range(n - 1):
            time.sleep(interval)
            readings.append(self.read())
        return sum(readings) / len(readings)

    def read_stable(
        self,
        *,
        window: int = 10,
        min_settle: float = 5.0,
        max_drift: float = 0.002,
        max_range: float = 0.03,
        stable_checks: int = 3,
        timeout: float = 300.0,
        interval: float = 1.0,
    ) -> float:
        # window=10 (not 5): the OLS slope's standard error is sigma/sqrt(Sum (t-tbar)^2),
        # ~sigma/3.2 at window=5 vs ~sigma/9 at window=10. With this probe's measured
        # per-reading noise sigma~=0.007 pH, a 5-sample window puts the slope SE (~0.0022)
        # ABOVE max_drift, so a settled probe fails the drift gate ~35% of the time on
        # noise alone; at window=10 the SE (~0.0008) sits well below it. max_range is 0.03
        # (not 0.02) because peak-to-peak grows with window size (E[ptp]~=3.1*sigma at
        # window=10 ~= 0.021), so the old 0.02 would reject settled windows outright.
        """Wait for the probe to settle, then return the settled pH.

        A reading is taken every
        *interval* seconds (the probe streams at ~1 Hz) into a rolling *window* of
        the most recent readings. Once the window is full and at least *min_settle*
        seconds have elapsed, each new window is scored on two criteria:

        Args:
            window:        Number of recent readings in the rolling window (>= 2).
            min_settle:    Minimum seconds before any window may be called stable.
            max_drift:     Max absolute regression slope (pH/second) to count stable.
            max_range:     Max peak-to-peak spread (pH) to count stable.
            stable_checks: Consecutive passing windows required (>= 1).
            timeout:       Give up after this many seconds without settling.
            interval:      Seconds between readings (~1.0 for the 1 Hz stream).

        Never raises on a timeout: if *timeout* elapses before the probe
        settles, a warning is printed (with the best/latest reading and the
        window's final drift/range) and that best-effort reading is returned
        instead - a slow-to-settle well shouldn't crash an otherwise-healthy
        run.

        Returns:
            The mean pH of the final settled window, or the best (latest
            valid) reading if *timeout* elapsed first.
        """
        monitor = _StabilityMonitor(
            window=window,
            min_settle=min_settle,
            max_drift=max_drift,
            max_range=max_range,
            stable_checks=stable_checks,
        )
        start = time.monotonic()
        last_valid = math.nan
        while True:
            value = self.read()
            elapsed = time.monotonic() - start
            if math.isfinite(value):
                last_valid = value
            if monitor.update(elapsed, value):
                return monitor.mean()
            if elapsed >= timeout:
                print(
                    f"WARNING: pH did not stabilize within {elapsed:.0f}s "
                    f"(last reading {last_valid:.3f}, drift {monitor.slope():+.4f} pH/s, "
                    f"range {monitor.ptp():.3f} pH) - using best-effort reading and continuing."
                )
                return last_valid
            time.sleep(interval)

    def wait_for(
        self,
        *,
        above: float | None = None,
        below: float | None = None,
        timeout: float = 300.0,
        interval: float = 5.0,
    ) -> float:
        """Block until pH crosses a threshold, then return the reading.

        ph = bench.ph.wait_for(above=7.0, timeout=120)
        ph = bench.ph.wait_for(below=5.0)
        """
        if above is None and below is None:
            raise ValueError("Specify above= or below= (or both).")
        deadline = time.monotonic() + timeout
        while True:
            ph = self.read()
            if (above is None or ph > above) and (below is None or ph < below):
                return ph
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"pH did not reach the target condition within {timeout:.0f}s "
                    f"(last reading: {ph:.2f})"
                )
            time.sleep(interval)

    def calibrate(self, point: str, value: float) -> None:
        """Calibrate the probe at a known buffer.

        Args:
            point: One of ``"mid"``, ``"low"``, ``"high"``, or ``"clear"``.
            value: Known pH of the calibration buffer.
        """
        self._p.PHSensor.Calibrate(Point=point, Value=value)
        _snapshot(self, f"calibrate_{point}")

    def set_temperature(self, celsius: float) -> None:
        """Set the temperature-compensation value used when computing pH.

        The probe assumes 25 C by default; set this to the actual buffer or
        sample temperature before calibrating or reading for accurate results.
        """
        self._p.PHSensor.SetTemperature(Temperature=celsius)
