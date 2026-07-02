"""Active toolhead configuration and mount-state tracking."""
from pathlib import Path

from rxn_bench_gantry.toolhead_config import ToolheadConfig, ToolheadGeometry

_TOOLHEADS_DIR = Path(__file__).parent / "toolheads"


class ToolheadManager:
    """Owns the currently active toolhead config and whether it is physically mounted."""

    def __init__(self) -> None:
        self._toolhead: ToolheadGeometry | None = None
        self._name: str = ""
        self._display_name: str = ""
        self._mounted: bool = False
        self._sensor_type: str | None = None

    @property
    def toolhead(self) -> ToolheadGeometry | None:
        return self._toolhead

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def mounted(self) -> bool:
        return self._mounted

    @property
    def sensor_type(self) -> str | None:
        return self._sensor_type

    def set_toolhead(self, name: str) -> None:
        """Load a toolhead config by name and activate it.

        Args:
            name: Toolhead name matching a config folder under ``toolheads/``.
        """
        cfg = ToolheadConfig.load(name)
        self._toolhead = cfg.geometry
        self._name = cfg.name
        self._display_name = cfg.display_name
        self._sensor_type = cfg.sensor_type

    def clear_toolhead(self) -> None:
        """Remove the active toolhead and reset all toolhead state to defaults."""
        self._toolhead = None
        self._name = ""
        self._display_name = ""
        self._mounted = False
        self._sensor_type = None

    def set_mounted(self, mounted: bool) -> None:
        """Update whether a toolhead is physically installed on the carriage.

        Args:
            mounted: True if the toolhead is physically attached.
        """
        self._mounted = mounted

    @staticmethod
    def list_toolheads() -> list[tuple[str, str]]:
        """Return [(name, display_name), …] for every installed toolhead config."""
        results = []
        for folder in sorted(_TOOLHEADS_DIR.iterdir()):
            if not folder.is_dir():
                continue
            yaml_path = folder / f"{folder.name}_toolhead.yaml"
            if yaml_path.exists():
                try:
                    cfg = ToolheadConfig.from_yaml(yaml_path)
                    results.append((cfg.name, cfg.display_name))
                except Exception:
                    pass
        return results
