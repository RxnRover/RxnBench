"""
CLI entry point. Installed as `chem-bench-mydevice`.

TODO: update the three TODO markers below — everything else can be copied as-is.
"""
import sys
from pathlib import Path

# TODO: rename mydevice to match your device (must match the filename in configs/)
_DEVICE_NAME = "mydevice"

_DEFAULT_CONFIGS = [
    Path.home() / ".chem_bench" / f"{_DEVICE_NAME}.json",
    Path("configs") / f"{_DEVICE_NAME}.json",
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
                f"Create one at ~/.chem_bench/{_DEVICE_NAME}.json or pass --config /path/to.json.\n"
                f"A template is at device_template/configs/{_DEVICE_NAME}.json in the repo."
            )
            sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "chem_bench_template.server:create_app",  # TODO: rename chem_bench_template
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
