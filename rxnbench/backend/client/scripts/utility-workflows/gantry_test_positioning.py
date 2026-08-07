# Created to test positioning and function of gantry
# Gantry hovers over each well in the workspace

from datetime import datetime
from rxn_bench_client import RxnBenchClient, Gantry


def main() -> None:
    # Keep your script inside this main() function to keep things simple.
    with RxnBenchClient() as bench:
        # Tell the bench which instruments you're using and where to find them.
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")

        # Tell the bench where to save your results.
        date = datetime.now().strftime("%m-%d-%y")
        bench.set_log_output("results/gantry_test_positioning" + date + ".csv")

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

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
