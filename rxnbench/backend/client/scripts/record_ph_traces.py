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

# --- What to record ----------------------------------------------------------

# Wells to sample, as "plate/well" labels in the active workspace. Pick a spread
# of pH values, buffers, and any awkward or slow-settling samples - the tuning
# is only as representative as this list.
TRACE_WELLS = [
    "Calibration/A2",  # pH 7 buffer
    "Calibration/A3",  # pH 4 buffer
]

# Seconds to record per well. Make this >= the longest timeout you want to
# evaluate offline, and long enough that the probe truly flattens by the end -
# the tail of each trace is used as its reference equilibrium value.
TRACE_SECONDS = 120.0

# Seconds between readings. The probe streams at ~1 Hz, so 1.0 captures every
# new value; matching read_stable's cadence keeps replay faithful to live runs.
SAMPLE_INTERVAL = 1.0

# Directory (relative to the working dir) to write one CSV per well.
OUTPUT_DIR = "ph_traces"

# Optional DI-water well to rinse between samples so carryover doesn't
# contaminate the next trace's equilibrium. Set to None to skip.
RINSE_WELL = "Wash-Station/A1"
RINSE_SECONDS = 30.0

# Buffer/sample temperature for compensation (the EZO assumes 25 C).
SAMPLE_TEMPERATURE_C = 25.0


def rinse_probe(bench) -> None:
    """Dip the probe in the rinse well to wash off the previous sample."""
    if RINSE_WELL is None:
        return
    print(f"Rinsing probe in {RINSE_WELL}...")
    bench.gantry.move_to_well(RINSE_WELL)
    bench.gantry.engage_tool()
    time.sleep(RINSE_SECONDS)
    bench.gantry.disengage_tool()


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


def main() -> None:
    with RxnBenchClient() as bench:
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        # Use whatever workspace is currently active in the UI.
        bench.gantry.load_workspace_yaml()
        bench.ph.set_temperature(SAMPLE_TEMPERATURE_C)

        out_dir = Path(OUTPUT_DIR)
        print(f"Recording {len(TRACE_WELLS)} pH traces into {out_dir}/ ...")
        for well in TRACE_WELLS:
            bench.check_pause_stop()  # honor the UI pause/stop button
            record_trace(bench, well, out_dir)
            rinse_probe(bench)

        bench.gantry.save_and_park()
        print(f"Done. Tune against them with:  python tune_endpoint.py {out_dir}")


if __name__ == "__main__":
    main()
