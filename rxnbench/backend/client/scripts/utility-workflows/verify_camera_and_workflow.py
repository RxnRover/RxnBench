# Quick smoke test: bench.start_experiment(), bench.workflow, and the camera
# working together via bench.devices auto-discovery (mDNS). No gantry
# movement - safe to run any time.

from pathlib import Path

from rxn_bench_client import RxnBenchClient


def main() -> None:
    with RxnBenchClient() as bench:
        bench.devices.gantry
        bench.devices.camera

        bench.gantry.load_workspace_yaml()

        folder = bench.start_experiment(__file__)
        print(f"Experiment folder: {folder}")

        bench.set_workflow_output(f"logs/{Path(__file__).stem}_workflow.jsonl")

        with bench.workflow.step("camera_snapshot", devices=["camera"], idempotent=True):
            image_path = folder / "snapshot.jpg"
            bench.camera.save_snapshot(str(image_path))
            print(f"Saved snapshot: {image_path} ({image_path.stat().st_size} bytes)")

        bench.log(status="ok", image_bytes=image_path.stat().st_size)

        print("All checks passed - see the experiment folder above.")


if __name__ == "__main__":
    main()
