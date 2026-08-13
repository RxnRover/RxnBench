import time
from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

# This script demonstrates how to use the bench to scan a plate of wells and log pH values.

def main() -> None:
    # For more exact control:
    with RxnBenchClient() as bench:
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        bench.start_experiment(__file__)
        bench.gantry.load_workspace_yaml()
        bench.gantry.confirm_toolhead_mounted()

        # You can move to any specific well directly if you know its label.
        bench.gantry.move_to_well("plate1/A1")
        bench.gantry.engage_tool()
        time.sleep(3)
        ph = bench.ph.read()
        bench.log(well="plate1/A1", ph=ph)
        bench.gantry.disengage_tool()

        # bench.ph.read_avg() takes several readings and averages them.
        for well in bench.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well):
                ph = bench.ph.read_avg(n=5, interval=1.0)
                bench.log(ph=ph)

        # bench.ph.read_stable() keeps reading until the probe settles
        # (low pH-vs-time drift and a tight peak-to-peak range).
        for well in bench.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well):
                ph = bench.ph.read_stable(max_range=0.05, timeout=60)
                bench.log(ph=ph)

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()


if __name__ == "__main__":
    main()
