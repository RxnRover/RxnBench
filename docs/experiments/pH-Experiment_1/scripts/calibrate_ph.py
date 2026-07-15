# Automatic calibration script for the Atlas Scientific EZO-pH probe.
#
# Runs a clean 2 or 3 point calibration in the order the EZO-pH circuit requires:
# the mid (pH 7) point resets any prior calibration and must be taken first,
# then the low (pH 4) and high (if 3 point) (pH 10) points refine the acid/base slope.

import time

from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

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

# Optional DI-water well to rinse the probe between buffers, avoiding carryover
# that would contaminate the next buffer. Set to None to skip (no rinse well).
RINSE_WELL = "Wash-Station/A1"  # e.g. "Calibration/A4"

# General wait times
SETTLE_SECONDS = 30

# Temperature of the calibration buffers, in degrees C. The EZO assumes 25 C by
# default; setting the real buffer temperature keeps the acid/base slopes from
# being skewed by the Nernstian temperature dependence of the electrode.
BUFFER_TEMPERATURE_C = 25.0


def rinse_probe(bench) -> None:
    """Dip the probe in the rinse well to wash off the previous buffer."""
    if RINSE_WELL is None:
        return
    print(f"Rinsing probe in {RINSE_WELL}...")
    bench.gantry.move_to_well(RINSE_WELL)
    bench.gantry.engage_tool()
    time.sleep(SETTLE_SECONDS)
    bench.gantry.disengage_tool()
    # TODO: Add method to vibrate the probe to shake off excess water before moving


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
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        # Record each buffer reading before/after calibration for your records.
        bench.set_log_output("ph_calibration.csv")

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        print(
            f"Starting pH calibration script with {len(CALIBRATION_POINTS)} points..."
        )
        print(
            f"Note: It is important that the pH probe is fully submerged into the solution, and that the solution is well-mixed before taking a reading."
        )
        print(
            f"      If the pH probe is not subermged increase the amount of solution, or adjust the engagement depth"
        )

        # Compensate readings for the buffer temperature before calibrating so
        # the acid/base slopes aren't skewed if the buffers aren't at 25 C.
        bench.ph.set_temperature(BUFFER_TEMPERATURE_C)

        # Start from a clean slate so stale calibration can't skew the result.
        print(f"Clearing any prior calibration...")
        bench.ph.calibrate("clear", 0.0)

        totalTimeBefore = time.time()

        for point, well, known_ph in CALIBRATION_POINTS:
            bench.check_pause_stop()  # honor the UI pause/stop button

            calibrate_point(bench, point, well, known_ph)

            # Wash after each buffer to avoid carryover that would contaminate the next buffer.
            rinse_probe(bench)

        # Read every well in the 24-Well plate now that the probe is calibrated.
        bench.set_log_output("ph_samples.csv", columns=["well", "ph"])
        sample_wells = bench.gantry.get_workspace_wells("24-well")
        print(f"Reading pH of {len(sample_wells)} wells in the 24-Well plate...")

        for well in sample_wells:
            bench.check_pause_stop()  # honor the UI pause/stop button

            # at_well moves to the well, engages the tool, and disengages on exit;
            # it also tags the log row with the current well automatically.
            with bench.at_well(well):
                beforeTime = time.time()
                print(f"Waiting for probe to settle in {well}...")
                ph = bench.ph.read_stable(timeout=120)
                afterTime = time.time()
                print(f"Probe settled in {afterTime - beforeTime:.1f} seconds.")
                bench.log(ph=ph, settling_time=afterTime - beforeTime)
                print(f"{well}: pH {ph:.2f}")

            # Wash between wells to avoid carryover from the previous sample.
            rinse_probe(bench)

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()

        totalTimeAfter = time.time()

        print(
            f"Total time for calibration and sample readings: {totalTimeAfter - totalTimeBefore:.1f} seconds."
        )

if __name__ == "__main__":
    main()
