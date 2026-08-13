"""Demo script: tour every well in the workspace, reading pH at a steady ~10s interval."""

import re
import time
from pathlib import Path

from rxn_bench_client import Camera, DosingPump, Gantry, PHProbe, RxnBenchClient

_WELL_RE = re.compile(r"^[^/]+/([A-Za-z])(\d+)$")


def _filter_wells(wells: list[str], *, rows: set[str] | None = None, min_col: int = 1) -> list[str]:
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

TOUR_PLATES = [
    ("24-well1", {}),
    ("24-well2", {}),
    ("24-well3", {}),
    ("24-well4", {}),
    ("24-well5", {}),
]

PACE_SECONDS = 10.0


STABILIZE_SECONDS = 3.0

RINSE_WELL = "Wash-Station/A1"
WASH_VOLUME_ML = 5.0


def rinse_probe(bench) -> None:
    if RINSE_WELL is None:
        return
    # move_to_well/engage_tool/dispense_and_wait/disengage_tool each
    # auto-snapshot on their own (see instruments/_util.py) - no manual
    # bench.snapshot() calls needed here.
    bench.gantry.move_to_well(RINSE_WELL)
    bench.gantry.engage_tool()
    bench.pump.dispense_and_wait(WASH_VOLUME_ML)
    time.sleep(2)
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

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        wells = []
        for plate_name, filter_kwargs in TOUR_PLATES:
            wells.extend(_filter_wells(bench.gantry.get_workspace_wells(plate_name), **filter_kwargs))

        print(
            f"Touring {len(wells)} wells at a ~{PACE_SECONDS:.0f}s cadence "
            f"(~{len(wells) * PACE_SECONDS / 60:.1f} min total)..."
        )

        devices = ["gantry", "ph"] + (["pump"] if RINSE_WELL is not None else [])
        for well in bench.workflow.remaining(wells, key=lambda w: f"well:{w}"):
            bench.check_pause_stop()
            start = time.monotonic()

            # Not idempotent (default): rinse_probe() dispenses real liquid,
            # so a step that failed partway needs a human to check before
            # it's safe to retry - see confirm_retry on bench.workflow.step.
            # at_well() moves+engages+disengages, each auto-snapshotting on
            # its own - only the read itself needs an explicit snapshot,
            # since PHProbe.read() is deliberately not auto-instrumented
            # (it's polled every ~1s inside read_stable() elsewhere).
            with bench.workflow.step(f"well:{well}", devices=devices):
                with bench.at_well(well, stabilize=STABILIZE_SECONDS):
                    ph = bench.ph.read()
                    bench.log(ph=ph)
                    print(f"{well}: pH {ph:.2f}")
                    bench.snapshot("read")

                rinse_probe(bench)

            elapsed = time.monotonic() - start
            if elapsed < PACE_SECONDS:
                time.sleep(PACE_SECONDS - elapsed)

        bench.gantry.save_and_park()
        print("Tour complete.")


if __name__ == "__main__":
    main()
