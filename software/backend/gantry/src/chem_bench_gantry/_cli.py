"""
CLI entry point for the Gantry SiLA server. Installed as `chem-bench-gantry`.

Usage:
    chem-bench-gantry
    chem-bench-gantry --config /path/to/gantry.json
    CHEM_BENCH_MOCK=1 chem-bench-gantry
"""
import sys
from pathlib import Path

_DEFAULT_CONFIGS = [
    Path.home() / ".chem_bench" / "gantry.json",
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
                "Create one at ~/.chem_bench/gantry.json or pass --config /path/to.json.\n"
                "A template is at gantry/configs/gantry.json in the repo."
            )
            sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "chem_bench_gantry.server:create_app",
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
