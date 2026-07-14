# Automatic calibration script for the pH probe

import time
from rxn_bench_client import RxnBenchClient, Gantry, PHProbe


def main() -> None:
    with RxnBenchClient() as bench:
        """Keep your script inside this main() function to keep things simple."""

        # Tell the bench which instruments you're using and where to find them.
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        # Tell the bench where to save your results.
        bench.set_log_output("results/ph_scan.csv")

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        # Mount the tool you want to use.
        bench.gantry.mount_toolhead("ph_probe")

        low_buffer_well = 'Calibration/A3'
        mid_buffer_well = 'Calibration/A2'
        high_buffer_well = 'Calibration/A1'

        buffer = ['mid', 'low', 'high']
        buffer_wells = [mid_buffer_well, low_buffer_well, high_buffer_well]
        buffer_ph_values = [7.0, 4.0, 10.0]

        for buffer, well, ph in zip(buffer, buffer_wells, buffer_ph_values):
            bench.gantry.move_to_well(well, True)
            bench.gantry.engage_toolhead()
            # wait for stable
            time.sleep(15)
            bench.ph.calibrate(buffer, ph)
            bench.gantry.disengage_toolhead()

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()

if __name__ == "__main__":
    main()
