"""Demo script: watch the pH steady-state stabilization algorithm converge live."""

import math
import time

from rxn_bench_client import Gantry, PHProbe, RxnBenchClient

DEMO_WELLS = [
    "24-well2/B3",
    "24-well2/B4",
    "24-well4/B3",
]

RINSE_WELL = "Wash-Station/A1"

def rinse_probe(bench) -> None:
    """Dip the probe in the rinse well to wash off the previous buffer."""
    if RINSE_WELL is None:
        return
    print(f"Rinsing probe in {RINSE_WELL}...")
    bench.gantry.move_to_well(RINSE_WELL)
    bench.gantry.engage_tool()
    bench.pump.dispense_and_wait(5)  # flush DI water over the probe
    bench.gantry.disengage_tool()
    bench.gantry.shake() # fling off excess liquid

def main() -> None:
    with RxnBenchClient() as bench:
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        bench.start_experiment(__file__)

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        print(f"Showcasing the stabilization algorithm on {len(DEMO_WELLS)} wells...")

        for well in DEMO_WELLS:
            rinse_probe(bench)
            bench.check_pause_stop()
            start = time.monotonic()

            with bench.at_well(well):
                ph = bench.ph.read_stable(timeout=300)
                elapsed = time.monotonic() - start
                bench.log(ph=ph, settling_time=elapsed)

        bench.gantry.save_and_park()
        print("\nDemo complete.")


if __name__ == "__main__":
    main()
