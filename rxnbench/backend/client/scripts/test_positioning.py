# Created to test positioning and function of gantry

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

        # Get the labels of all wells in the workspace
        wells: list[str] = bench.gantry.get_workspace_wells()
        bench.log(wells=wells)  # log the well labels for reference

        # Move to but do not engage to each well in the workspace
        for well in wells:
            bench.gantry.move_to_well(well, True)

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()

if __name__ == "__main__":
    main()
