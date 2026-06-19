"""
CLI entry point. Installed as the `chem-bench` command.

Usage:
    chem-bench                          # auto-discovers config.json in cwd
    chem-bench --config /path/to/config.json
"""
import sys
from pathlib import Path


def main() -> None:
    config = Path("config.json")

    # Allow --config override
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        config = Path(sys.argv[idx + 1])

    if not config.exists():
        print(f"Error: config file not found at '{config}'")
        print("Run 'config create --app chem_bench.__main__:create_app' to generate one.")
        sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "chem_bench.__main__:create_app",
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
