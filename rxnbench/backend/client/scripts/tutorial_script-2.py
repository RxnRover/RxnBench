import time
from rxn_bench_client import RxnBenchClient, Gantry, PHProbe

# This script demonstrates how to use more exact control over the bench, including reading and logging pH values in different ways.

def main() -> None:
    with RxnBenchClient() as bench:
        """Keep your script inside this main() function to keep things simple."""

        # Tell the bench which instruments you're using and where to find them.
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        bench.connect("ph", PHProbe, server="pH")

        bench.set_log_output("results/ph_scan_manual.csv")
        bench.gantry.load_workspace_yaml()
        bench.gantry.set_toolhead("ph_probe")
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

        # bench.ph.read_stable() keeps reading until the value settles.
        for well in bench.gantry.get_workspace_wells("plate1"):
            with bench.at_well(well):
                ph = bench.ph.read_stable(tolerance=0.05, timeout=60)
                bench.log(ph=ph)

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()


if __name__ == "__main__":
    main()
