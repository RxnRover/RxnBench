from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

# This script demonstrates how to use logical control to react to readings.

def main() -> None:
    # Keep your script inside this main() function to keep things simple.
    with RxnBenchClient() as bench:
        # Tell the bench which instruments you're using and where to find them.
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        bench.start_experiment(__file__)
        bench.gantry.load_workspace_yaml()

        # Read a well and branch depending on the result.
        with bench.at_well("plate1/A1", stabilize=3):
            ph = bench.ph.read()

        if ph < 7.0:
            print(f"pH is acidic ({ph:.2f}), moving to A2 ...")
            bench.gantry.move_to_well("plate1/A2")
        else:
            print(f"pH is basic ({ph:.2f}), moving to A3 ...")
            bench.gantry.move_to_well("plate1/A3")

        # bench.ph.wait_for() blocks until the solution crosses a threshold.
        for well in bench.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well):
                ph = bench.ph.wait_for(above=7.0, timeout=120, interval=5)
                bench.log(ph=ph)

        # Always save and park at the end of a script
        bench.gantry.save_and_park()

if __name__ == "__main__":
    main()
