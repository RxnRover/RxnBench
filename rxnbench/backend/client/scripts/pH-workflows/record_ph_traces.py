# Record full pH settling traces for endpoint-detector validation.
#
# Instead of stopping early like read_stable(), this parks the probe in each
# well and logs the ENTIRE pH-vs-time trace for a fixed duration. Replaying the
# endpoint detector offline over these traces (see tune_endpoint.py) lets you
# tune the stability thresholds against THIS probe's real settling behavior,
# using the near-final average of each trace as the reference equilibrium value.
#
# Needs live hardware. The analysis half (tune_endpoint.py) runs without it.

import time
from pathlib import Path

from rxn_bench_client import RxnBenchClient, Gantry, PHProbe, DataLogger


TRACE_WELLS: list[str] = []
SAMPLE_PLATE_NAME = "24-well"
TRACE_SECONDS = 300.0
SAMPLE_INTERVAL = 1.0
OUTPUT_DIR = "ph_traces"

RINSE_WELL = "Wash-Station/A1"
RINSE_SECONDS = 30.0

SAMPLE_TEMPERATURE_C = 25.0

CALIBRATE_FIRST = True

MID_BUFFER_WELL = "Calibration/A2"   # pH 7 buffer  (calibrated first - resets the probe)
LOW_BUFFER_WELL = "Calibration/A3"   # pH 4 buffer
HIGH_BUFFER_WELL = "Calibration/A1"  # pH 10 buffer

CALIBRATION_POINTS = [
    ("mid", MID_BUFFER_WELL, 7.0),
    ("low", LOW_BUFFER_WELL, 4.0),
    ("high", HIGH_BUFFER_WELL, 10.0),
]

# Seconds to wait for the reading to stabilize before committing a point.
CALIBRATION_TIMEOUT = 300.0


def rinse_probe(bench) -> None:
    """Dip the probe in the rinse well to wash off the previous sample."""
    if RINSE_WELL is None:
        return
    print(f"Rinsing probe in {RINSE_WELL}...")
    bench.gantry.move_to_well(RINSE_WELL)
    bench.gantry.engage_tool()
    time.sleep(RINSE_SECONDS)
    bench.gantry.disengage_tool()
    bench.gantry.shake()  # fling off excess liquid


def record_trace(bench, well: str, out_dir: Path) -> None:
    """Park in *well* and log the full pH trace to ``out_dir/<well>.csv``."""
    path = out_dir / f"{well.replace('/', '_')}.csv"
    print(f"Recording {TRACE_SECONDS:.0f}s trace in {well} -> {path}")
    # stabilize=0: capture the settling from the moment the probe is submerged.
    with bench.at_well(well), DataLogger(path, columns=["t", "ph"]) as log:
        start = time.monotonic()
        while True:
            t = time.monotonic() - start
            log.record(t=round(t, 3), ph=bench.ph.read())
            if t >= TRACE_SECONDS:
                break
            time.sleep(SAMPLE_INTERVAL)


def calibrate_point(bench, point: str, well: str, known_ph: float) -> None:
    """Calibrate the probe at a single buffer point."""
    bench.check_pause_stop()  # honor the UI pause/stop button

    bench.gantry.move_to_well(well)
    bench.gantry.engage_tool()

    # Let the probe settle, then wait for the reading to stabilize before
    # committing this calibration point.
    print("Waiting for probe to settle...")
    before = bench.ph.read_stable(timeout=CALIBRATION_TIMEOUT)
    print(
        f"Calibrating {point} point in {well} (known pH {known_ph:.2f}) - current reading is {before:.2f}"
    )
    bench.ph.calibrate(point, known_ph)

    # A correctly-calibrated point should now read close to the buffer value.
    after = bench.ph.read_stable(timeout=120)
    print(f"{point:>4} @ pH {known_ph:5.2f}: before={before:.2f}  after={after:.2f}")

    bench.gantry.disengage_tool()


def calibrate_probe(bench) -> None:
    """Run a clean 3-point calibration before recording any traces."""
    print(f"Calibrating probe ({len(CALIBRATION_POINTS)} points) before recording...")
    print(
        "Note: the pH probe must be fully submerged and the buffer well-mixed before "
        "each reading; increase the buffer volume or engagement depth if it is not."
    )

    # Start from a clean slate so stale calibration can't skew the traces.
    print("Clearing any prior calibration...")
    bench.ph.calibrate("clear", 0.0)

    for point, well, known_ph in CALIBRATION_POINTS:
        bench.check_pause_stop()  # honor the UI pause/stop button
        calibrate_point(bench, point, well, known_ph)
        # Wash after each buffer to avoid carryover into the next.
        rinse_probe(bench)


def main() -> None:
    with RxnBenchClient() as bench:
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        # Use whatever workspace is currently active in the UI.
        bench.gantry.load_workspace_yaml()
        bench.ph.set_temperature(SAMPLE_TEMPERATURE_C)

        # Optionally calibrate first so the traces reflect a freshly calibrated probe.
        if CALIBRATE_FIRST:
            calibrate_probe(bench)

        # Fall back to every well in the sample plate when no explicit list is given.
        trace_wells = TRACE_WELLS or bench.gantry.get_workspace_wells(SAMPLE_PLATE_NAME)

        out_dir = Path(OUTPUT_DIR)
        print(f"Recording {len(trace_wells)} pH traces into {out_dir}/ ...")
        for well in trace_wells:
            bench.check_pause_stop()  # honor the UI pause/stop button
            record_trace(bench, well, out_dir)
            bench.gantry.shake()
            rinse_probe(bench)

        bench.gantry.save_and_park()
        print(f"Done. Tune against them with:  python tune_endpoint.py {out_dir}")


if __name__ == "__main__":
    main()
