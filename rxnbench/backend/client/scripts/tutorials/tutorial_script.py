from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

# This script demonstrates how to use the bench to scan a plate of wells and log pH values.

def main() -> None:
    # Keep your script inside this main() function to keep things simple.
    with RxnBenchClient() as bench:
        # Tell the bench which instruments you're using and where to find them.
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        # Tell the bench where to save your results.
        bench.set_log_output("results/ph_scan.csv")

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        # Scan every well in a plate. at_well() moves to the well, engages
        # the tool, waits for it to stabilise, then lifts back up automatically.
        for well in bench.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well, stabilize=3):
                bench.log(ph=bench.ph.read())  # well is saved to the log automatically

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()

if __name__ == "__main__":
    main()
