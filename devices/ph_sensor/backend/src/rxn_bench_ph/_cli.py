"""
CLI entry point for the pH Sensor SiLA server. Installed as `rxn-bench-ph`.

Usage:
    rxn-bench-ph
    rxn-bench-ph --config /path/to/ph_sensor.json
    RXN_BENCH_MOCK=1 rxn-bench-ph
"""
import sys
from pathlib import Path

_DEFAULT_CONFIGS = [
    Path.home() / ".rxn_bench" / "ph_sensor.json",
    Path("configs") / "ph_sensor.json",
]


def main() -> None:
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        config = Path(sys.argv[idx + 1])
    else:
        config = next((c for c in _DEFAULT_CONFIGS if c.exists()), None)
        if config is None:
            print(
                "Error: no pH sensor config found.\n"
                "Create one at ~/.rxn_bench/ph_sensor.json or pass --config /path/to.json.\n"
                "A template is at ph_sensor/configs/ph_sensor.json in the repo."
            )
            sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "rxn_bench_ph.server:create_app",
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
