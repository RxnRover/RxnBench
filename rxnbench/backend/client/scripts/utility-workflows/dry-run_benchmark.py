import time
from rxn_bench_client import RxnBenchClient, Gantry

# This script demonstrates how to use more exact control over the bench, including reading and logging pH values in different ways.

def main() -> None:
    # Keep your script inside this main() function to keep things simple.
    with RxnBenchClient() as bench:
        # Tell the bench which instruments you're using and where to find them.
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")

        bench.start_experiment(__file__)
        bench.gantry.load_workspace_yaml() ## Load current workspace

        # Get the labels of all wells in the workspace
        wells: list[str] = bench.gantry.get_workspace_wells()
        bench.log(wells=wells)  # log the well labels for reference

        startTime = time.time()

        print(f"Beginning benchmarking tests")
        
        print(f"Moving from corner to corner")
        # Move from accessible corner to corner in the workspace

        currentRunSeconds = startTime - time.time()
        print(f"Complete " + currentRunSeconds + " seconds")

        print(f"Moving to each well in the workspace (no-engage)")
        # Move to but do not engage to each well in the workspace
        for well in wells:
            bench.gantry.move_to_well(well, True)

        print(f"Complete" + currentRunSeconds)
        bench.gantry.save_and_park()
        
        print(f"Engaging each well in the workspace (engage)")
        # Move to and engage each well in the workspace
        for well in wells:
            bench.gantry.move_to_well(well)
            bench.gantry.engage_tool()
            bench.log("Engage")
            bench.gantry.disengage_tool()
            bench.log("Disengage")

        print(f"Complete" + currentRunSeconds)

        print(f"Shaking toolhead 100 times")
        for i in range(100):
            print(f"Shaking: " + (i+1) + " times")
            bench.gantry.shake()

        print(f"Complete" + currentRunSeconds)

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()

        totalTime = time.time() - startTime
        print(f"Completed in {totalTime:.1f} seconds.")


if __name__ == "__main__":
    main()
