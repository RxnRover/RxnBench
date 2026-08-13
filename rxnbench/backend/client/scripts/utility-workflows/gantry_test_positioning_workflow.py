# Created to test positioning and function of gantry

from pathlib import Path
from rxn_bench_client import RxnBenchClient, Gantry, Camera


def main() -> None:
    # Keep your script inside this main() function to keep things simple.
    with RxnBenchClient() as bench:
        # Tell the bench which instruments you're using and where to find them.
        # Server names are discovered automatically on the local network.
        bench.connect("gantry", Gantry, server="Gantry")
        # Optional - remove if you don't want per-well photos.
        bench.connect("camera", Camera, server="Camera")

        bench.start_experiment(__file__)

        # Stable, no timestamp - needed so a resumed run finds the same
        # manifest, and so the Experiment Runner's resume prompt can find it.
        bench.set_workflow_output(f"logs/{Path(__file__).stem}_workflow.jsonl")

        # Load the workspace that's currently active in the UI.
        bench.gantry.load_workspace_yaml()

        wells: list[str] = bench.gantry.get_workspace_wells()
        bench.log(wells=wells)

        # remaining() skips any well already visited on a prior run.
        for well in bench.workflow.remaining(wells, key=lambda w: f"well:{w}"):
            bench.check_pause_stop()
            # idempotent=True: just a move, always safe to retry.
            with bench.workflow.step(f"well:{well}", devices=["gantry"], idempotent=True):
                bench.gantry.move_to_well(well, True)

        # Always save and park at the end of a script.
        bench.gantry.save_and_park()

if __name__ == "__main__":
    main()
