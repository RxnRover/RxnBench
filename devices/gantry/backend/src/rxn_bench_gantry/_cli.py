"""
CLI entry point for the Gantry SiLA server. Installed as `rxn-bench-gantry`.

Usage:
    rxn-bench-gantry
    rxn-bench-gantry --config /path/to/gantry.json
    RXN_BENCH_MOCK=1 rxn-bench-gantry
"""
import sys
from pathlib import Path

_DEFAULT_CONFIGS = [
    Path.home() / ".rxn_bench" / "gantry.json",
    Path("configs") / "gantry.json",
]


def main() -> None:
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        config = Path(sys.argv[idx + 1])
    else:
        config = next((c for c in _DEFAULT_CONFIGS if c.exists()), None)
        if config is None:
            print(
                "Error: no gantry config found.\n"
                "Create one at ~/.rxn_bench/gantry.json or pass --config /path/to.json.\n"
                "A template is at gantry/configs/gantry.json in the repo."
            )
            sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "rxn_bench_gantry.server:create_app",
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
