"""CLI entry point. Installed as `rxn-bench-dosing-pump`."""
import sys
from pathlib import Path

_DEVICE_NAME = "dosing_pump"

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_CONFIGS = [
    Path.home() / ".rxn_bench" / f"{_DEVICE_NAME}.json",
    _PACKAGE_ROOT / "configs" / f"{_DEVICE_NAME}.json",
]


def main() -> None:
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        config = Path(sys.argv[idx + 1])
    else:
        config = next((c for c in _DEFAULT_CONFIGS if c.exists()), None)
        if config is None:
            print(
                f"Error: no {_DEVICE_NAME} config found.\n"
                f"Create one at ~/.rxn_bench/{_DEVICE_NAME}.json or pass --config /path/to.json.\n"
                f"A default ships at devices/dosing_pump/capability/backend/configs/{_DEVICE_NAME}.json."
            )
            sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "rxn_bench_dosing_pump.server:create_app",
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
