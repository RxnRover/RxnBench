"""
CLI entry point for the Camera SiLA server. Installed as `rxn-bench-camera`.

Usage:
    rxn-bench-camera
    rxn-bench-camera --config /path/to/camera.json
    RXN_BENCH_MOCK=1 rxn-bench-camera
"""
import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_CONFIGS = [
    Path.home() / ".rxn_bench" / "camera.json",
    _PACKAGE_ROOT / "configs" / "camera.json",
]


def main() -> None:
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        config = Path(sys.argv[idx + 1])
    else:
        config = next((c for c in _DEFAULT_CONFIGS if c.exists()), None)
        if config is None:
            print(
                "Error: no camera config found.\n"
                "Create one at ~/.rxn_bench/camera.json or pass --config /path/to.json.\n"
                "A template is at devices/camera/capability/backend/configs/camera.json in the repo."
            )
            sys.exit(1)

    sys.argv = [
        "connector", "start",
        "--app", "rxn_bench_camera.server:create_app",
        "--config-path", str(config),
    ]

    from unitelabs.cdk.cli import connector
    connector()
