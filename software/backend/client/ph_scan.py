#!/usr/bin/env python3
"""
Single-plate pH scan script.

Moves to each well in sequence, engages the probe, waits for the reading
to settle, records the pH, disengages, then moves on.

Usage:
    uv run python ph_scan.py
    uv run python ph_scan.py --wells A1 B1 C1 D1 E1 F1 G1 H1
    uv run python ph_scan.py --settle 3 --delay 10
    uv run python ph_scan.py --plate reagents --workspace my_setup

The default workspace (defined inline below) places a single 96-well plate
at origin (50, 30) mm. Edit WORKSPACE_YAML to match your physical deck.
"""
from __future__ import annotations

import argparse
import sys
import time

from chem_bench_client import ChemBenchClient

# ---------------------------------------------------------------------------
# Workspace — edit to match your deck layout
# ---------------------------------------------------------------------------
WORKSPACE_YAML = """\
name: ph_scan
calibration_reference_well: plate1/A1
plates:
  - id: plate1
    plate_type: 96_well_standard
    origin:
      x: 50.0
      y: 30.0
      z: 15.0
    orientation: standard
"""

DEFAULT_WELLS = ["A1", "A2", "A3", "A4", "A5", "A6"]
SETTLE_SECS   = 2.0   # seconds between engage and reading
STARTUP_DELAY = 5     # countdown before first move


# ---------------------------------------------------------------------------
# Scan logic
# ---------------------------------------------------------------------------

def run_scan(
    wells: list[str],
    plate: str,
    settle: float,
    workspace_yaml: str,
) -> dict[str, float]:
    results: dict[str, float] = {}

    with ChemBenchClient() as bench:
        print("Connecting … loading workspace")
        bench.load_workspace_yaml(workspace_yaml)

        print("Setting toolhead: ph_probe")
        bench.set_toolhead("ph_probe")
        # Give the ToolheadInfo observable property a moment to update
        # so engage_tool() can read the correct ZEngage depth.
        time.sleep(0.5)
        bench.confirm_toolhead_mounted()

        print(f"\nScanning {len(wells)} wells on plate '{plate}'\n")

        for well in wells:
            label = f"{plate}/{well}"

            _step(f"Moving  → {label}")
            bench.move_to_well(label)
            _ok()

            _step("Engaging tool")
            bench.engage_tool()
            _ok()

            _step(f"Settling {settle:.0f}s")
            time.sleep(settle)
            _ok()

            ph = bench.read_ph()
            results[well] = ph
            print(f"\r    pH {ph:6.3f}  ✓")

            _step("Disengaging")
            bench.disengage_tool()
            _ok()
            print()

        try:
            print("Parking gantry …")
            bench.save_and_park()
        except Exception as exc:
            print(f"    (park skipped: {exc})")
        print("Done.\n")

    return results


def _step(msg: str) -> None:
    print(f"    {msg:<22}", end="", flush=True)


def _ok() -> None:
    print(" ✓", flush=True)


# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

def print_results(results: dict[str, float]) -> None:
    if not results:
        print("No results.")
        return

    ph_vals = list(results.values())
    avg     = sum(ph_vals) / len(ph_vals)
    lo, hi  = min(ph_vals), max(ph_vals)

    bar_scale = 0.8  # chars per pH unit
    print("\n" + "═" * 42)
    print("  pH Scan Results")
    print("═" * 42)
    for well, ph in results.items():
        bar = "█" * max(1, round(ph * bar_scale))
        print(f"  {well:>4}   {ph:6.3f}  {bar}")
    print("─" * 42)
    print(f"  mean   {avg:6.3f}")
    print(f"  range  {lo:.3f} – {hi:.3f}")
    print("═" * 42)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move to each well, engage the pH probe, record a reading."
    )
    parser.add_argument(
        "--wells", nargs="+", default=DEFAULT_WELLS, metavar="WELL",
        help=f"Wells to scan (default: {' '.join(DEFAULT_WELLS)})",
    )
    parser.add_argument(
        "--plate", default="plate1", metavar="ID",
        help="Plate ID in the workspace (default: plate1)",
    )
    parser.add_argument(
        "--settle", type=float, default=SETTLE_SECS, metavar="SEC",
        help=f"Seconds to wait after engaging before reading (default: {SETTLE_SECS})",
    )
    parser.add_argument(
        "--delay", type=int, default=STARTUP_DELAY, metavar="SEC",
        help=f"Countdown before first move (default: {STARTUP_DELAY})",
    )
    args = parser.parse_args()

    print(f"\nChem Bench — pH Scan")
    print(f"Wells : {', '.join(args.wells)}  on plate '{args.plate}'")
    print(f"Settle: {args.settle}s per well")
    print()

    for i in range(args.delay, 0, -1):
        print(f"\rStarting in {i}…  ", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 30 + "\r", end="")

    try:
        results = run_scan(args.wells, args.plate, args.settle, WORKSPACE_YAML)
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)

    print_results(results)


if __name__ == "__main__":
    main()
