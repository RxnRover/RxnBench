# Automatic calibration / sampling script for the pH toolhead on Rxn Bench

import re
import time

from rxn_bench_client import RxnBenchClient, Gantry, PHProbe, DosingPump

_WELL_RE = re.compile(r'^[^/]+/([A-Za-z])(\d+)$')


def _filter_wells(wells: list[str], *, rows: set[str] | None = None, min_col: int = 1) -> list[str]:
    """Keep only wells with a row in *rows* (None = any row) and column >= *min_col*.

    Used to skip wells that physically have no sample in them - e.g. an
    unfilled column 1, or unfilled rows on a partially-loaded plate.
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

# --- Calibration setup -------------------------------------------------------
# Wells holding each buffer, as "plate/well" labels in the active workspace.
MID_BUFFER_WELL = "Calibration/A2"  # pH 7 buffer  (calibrated first - resets the probe)
LOW_BUFFER_WELL = "Calibration/A3"  # pH 4 buffer
# HIGH_BUFFER_WELL = "Calibration/A1"  # pH 10 buffer

# (point name, well, known buffer pH). Order matters: "mid" MUST come first.
CALIBRATION_POINTS = [
    ("mid", MID_BUFFER_WELL, 7.0),
    ("low", LOW_BUFFER_WELL, 4.0),
    # ("high", HIGH_BUFFER_WELL, 10.0),
]

# --- Logging setup -----------------------------------------------------------
PH_CALIBRATION_LOG_FILE = "ph_calibration.csv"
SAMPLE_LOG_FILE = "ph_sample.csv"

# --- Sampling setup -----------------------------------------------------------
# (plate name, well filter kwargs for _filter_wells). Plate 1 is only loaded in
# A2-A6 and B2-B6 (column 1 and rows C/D are empty); plates 2 and 3 are fully
# loaded except for column 1.
SAMPLE_PLATES = [
    ("24-well1", {"rows": {"A", "B"}, "min_col": 2}),
    ("24-well2", {"min_col": 2}),
    ("24-well3", {"min_col": 2}),
]


# --- Working parameters -----------------------------------------------------------

# Optional DI-water well to rinse the probe between buffers, avoiding carryover
# that would contaminate the next buffer. Set to None to skip (no rinse well).
RINSE_WELL = "Wash-Station/A1"  # e.g. "Calibration/A4"

# General wait times
SETTLE_SECONDS = 5

# Volume of DI water the pump dispenses into the wash well once the probe is engaged.
WASH_VOLUME_ML = 5.0

# Temperature of the calibration buffers, in degrees C. The EZO assumes 25 C by
# default;
BUFFER_TEMPERATURE_C = 25.0


def rinse_probe(bench) -> None:
    """Dip the probe in the rinse well to wash off the previous buffer."""
    if RINSE_WELL is None:
        return
    print(f"Rinsing probe in {RINSE_WELL}...")
    bench.gantry.move_to_well(RINSE_WELL)
    bench.gantry.engage_tool()
    bench.pump.dispense_and_wait(WASH_VOLUME_ML)  # flush DI water over the probe
    time.sleep(SETTLE_SECONDS)
    bench.gantry.disengage_tool()
    bench.gantry.shake() # fling off excess liquid


def calibrate_point(bench, point: str, well: str, known_ph: float) -> None:
    """Calibrate the probe at a single point."""
    bench.check_pause_stop()  # honor the UI pause/stop button

    bench.gantry.move_to_well(well)
    bench.gantry.engage_tool()

    # Let the probe settle, then wait for the reading to stabilize before
    # committing this calibration point.
    print(f"Waiting for probe to settle...")
    beforeTime = time.time()
    before = bench.ph.read_stable(timeout=300)
    afterTime = time.time()
    print(f"Probe settled in {afterTime - beforeTime:.1f} seconds.")
    print(
        f"Calibrating {point} point in {well} (known pH {known_ph:.2f}) - current reading is {before:.2f}"
    )
    bench.ph.calibrate(point, known_ph)

    # A correctly-calibrated point should now read close to the buffer value.
    after = bench.ph.read_stable(timeout=120)
    bench.log(
        point=point,
        buffer_ph=known_ph,
        before=before,
        after=after,
        settling_time=afterTime - beforeTime,
    )
    print(f"{point:>4} @ pH {known_ph:5.2f}: before={before:.2f}  after={after:.2f}")

    bench.gantry.disengage_tool()


def main() -> None:
    with RxnBenchClient() as bench:
        # Tell the bench which instruments you're using and where to find them.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")
        bench.connect("pump", DosingPump, server="Dosing Pump")

        # Record each buffer reading before/after calibration for your records.
        bench.set_log_output(PH_CALIBRATION_LOG_FILE)

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        print(f"Starting pH calibration script with {len(CALIBRATION_POINTS)} points...")
        print(
            f"Note: It is important that the pH probe is fully submerged into the solution, and that the solution is well-mixed before taking a reading."
        )
        print(
            f"      If the pH probe is not submerged, increase the amount of solution, or adjust the engagement depth"
        )

        # Compensate readings for the buffer temperature
        bench.ph.set_temperature(BUFFER_TEMPERATURE_C)

        # Start from a clean slate so stale calibration can't skew the result.
        print(f"Clearing any prior calibration...")
        bench.ph.calibrate("clear", 0.0)

        startTime = time.time()

        for point, well, known_ph in CALIBRATION_POINTS:
            bench.check_pause_stop()  # honor the UI pause/stop button

            calibrate_point(bench, point, well, known_ph)

            # Wash after each buffer to avoid carryover that would contaminate the next buffer.
            rinse_probe(bench)

        # Read every well in each sample plate now that the probe is calibrated.
        bench.set_log_output(SAMPLE_LOG_FILE, columns=["well", "ph", "settling_time"])
        for plate_name, filter_kwargs in SAMPLE_PLATES:
            wells = _filter_wells(bench.gantry.get_workspace_wells(plate_name), **filter_kwargs)
            print(f"Reading pH of {len(wells)} wells in the {plate_name} plate...")

            for well in wells:
                bench.check_pause_stop()  # honor the UI pause/stop button

                # at_well moves to the well, engages the tool, and disengages on exit;
                # it also tags the log row with the current well automatically.
                with bench.at_well(well):
                    beforeTime = time.time()
                    print(f"Waiting for probe to settle in {well}...")
                    ph = bench.ph.read_stable(timeout=300)
                    afterTime = time.time()
                    print(f"Probe settled in {afterTime - beforeTime:.1f} seconds.")
                    bench.log(ph=ph, settling_time=afterTime - beforeTime)
                    print(f"{well}: pH {ph:.2f}")

                # Wash between wells to avoid carryover from the previous sample.
                rinse_probe(bench)

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()

        totalTime = time.time() - startTime
        print(f"Completed in {totalTime:.1f} seconds.")


if __name__ == "__main__":
    main()
