# Sample pH across every loaded well plate, with a rinse between wells and
# automatic per-action photos (if a camera is attached) - assumes the probe
# is *already calibrated*. Does not calibrate anything itself; run
# calibrate_ph.py (or the calibration half of pH_calibrate_and_sample.py)
# first if it isn't.

import re
import time
from pathlib import Path

from rxn_bench_client import Camera, DosingPump, Gantry, PHProbe, RxnBenchClient

_WELL_RE = re.compile(r"^[^/]+/([A-Za-z])(\d+)$")


def _filter_wells(wells: list[str], *, rows: set[str] | None = None, min_col: int = 1) -> list[str]:
    """Keep only wells with a row in *rows* (None = any row) and column >= *min_col*.

    Used to skip wells that physically have no sample in them.
    """
    kept = []
    for well in wells:
        m = _WELL_RE.match(well)
        if not m:
            continue
        row, col = m.group(1).upper(), int(m.group(2))
        if rows is not None and row not in rows:
            continue
        if col < min_col:
            continue
        kept.append(well)
    return kept


# (plate name, well filter kwargs for _filter_wells) - edit per your actual
# loaded wells, same shape as pH_calibrate_and_sample.py's SAMPLE_PLATES.
SAMPLE_PLATES = [
    ("24-well1", {"rows": {"A", "B"}, "min_col": 2}),
    ("24-well2", {"min_col": 2}),
    ("24-well3", {"min_col": 2}),
]

RINSE_WELL = "Wash-Station/A1"  # None to skip rinsing between wells
WASH_VOLUME_ML = 5.0
SETTLE_SECONDS = 5


def rinse_probe(bench) -> None:
    if RINSE_WELL is None:
        return
    bench.gantry.move_to_well(RINSE_WELL)
    bench.gantry.engage_tool()
    bench.pump.dispense_and_wait(WASH_VOLUME_ML)
    time.sleep(SETTLE_SECONDS)
    bench.gantry.disengage_tool()
    bench.gantry.shake()


def main() -> None:
    with RxnBenchClient() as bench:
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")
        if RINSE_WELL is not None:
            bench.connect("pump", DosingPump, server="Dosing Pump")
        # Optional - remove if you don't want per-well photos.
        bench.connect("camera", Camera, server="Camera")

        bench.start_experiment(__file__)
        bench.set_workflow_output(f"logs/{Path(__file__).stem}_workflow.jsonl")
        bench.set_log_output(bench.experiment_dir / "ph_sample.csv", columns=["well", "ph", "settling_time"])

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        devices = ["gantry", "ph"] + (["pump"] if RINSE_WELL is not None else [])

        for plate_name, filter_kwargs in SAMPLE_PLATES:
            wells = _filter_wells(bench.gantry.get_workspace_wells(plate_name), **filter_kwargs)
            print(f"Reading pH of {len(wells)} wells in the {plate_name} plate...")

            for well in bench.workflow.remaining(wells, key=lambda w: f"well:{w}"):
                bench.check_pause_stop()

                # Not idempotent (default): rinse_probe() dispenses real
                # liquid, so a step that failed partway needs a human to
                # check before it's safe to retry.
                with bench.workflow.step(f"well:{well}", devices=devices):
                    with bench.at_well(well):
                        beforeTime = time.time()
                        print(f"Waiting for probe to settle in {well}...")
                        ph = bench.ph.read_stable(timeout=300)
                        settling_time = time.time() - beforeTime
                        bench.log(ph=ph, settling_time=settling_time)
                        bench.snapshot("read")  # PHProbe.read() isn't auto-instrumented
                        print(f"{well}: pH {ph:.2f} (settled in {settling_time:.1f}s)")

                    rinse_probe(bench)

        bench.gantry.save_and_park()
        print("Sampling tour complete.")


if __name__ == "__main__":
    main()
