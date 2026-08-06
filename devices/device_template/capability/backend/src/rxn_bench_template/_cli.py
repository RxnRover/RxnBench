"""
CLI entry point. Installed as `rxn-bench-mydevice`.

TODO: update the three TODO markers below - everything else can be copied as-is.
"""
import sys
from pathlib import Path

# TODO: rename mydevice to match your device (must match the filename in configs/)
_DEVICE_NAME = "mydevice"

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
                f"A template is at device_template/configs/{_DEVICE_NAME}.json in the repo."
            )
            sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "rxn_bench_template.server:create_app",  # TODO: rename rxn_bench_template
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
