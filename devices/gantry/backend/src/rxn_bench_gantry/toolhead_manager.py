"""Active toolhead configuration and per-head mount-state tracking."""
import logging
from pathlib import Path

from rxn_bench_gantry.toolhead_config import ToolheadConfig, ToolheadGeometry

_TOOLHEADS_DIR = Path(__file__).parent / "toolheads"
_log = logging.getLogger(__name__)


class ToolheadManager:
    """Owns the currently active toolhead config and per-head mount confirmations.

    Several toolheads can be physically mounted on the carriage at once;
    exactly one is *active* (its geometry drives targeting and bounds).
    Mount confirmations are recorded per toolhead name and persist across
    activation switches, so a script can switch between two pre-confirmed
    heads without operator interaction.
    """

    def __init__(self) -> None:
        self._toolhead: ToolheadGeometry | None = None
        self._name: str = ""
        self._display_name: str = ""
        self._mounted_names: set[str] = set()
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
        """True if the *active* toolhead is confirmed physically mounted."""
        return bool(self._name) and self._name in self._mounted_names

    @property
    def mounted_toolheads(self) -> list[str]:
        """Names of every toolhead confirmed as physically mounted, sorted."""
        return sorted(self._mounted_names)

    @property
    def sensor_type(self) -> str | None:
        return self._sensor_type

    def set_toolhead(self, name: str) -> None:
        """Activate a toolhead config by name - a pure software switch.

        Mount confirmations are per-head and survive switching: activating a
        head that was already confirmed mounted needs no re-confirmation, so
        scripts can alternate between two mounted heads unattended.

        Args:
            name: Toolhead name matching a config folder under ``toolheads/``.
        """
        cfg = ToolheadConfig.load(name)
        self._toolhead = cfg.geometry
        self._name = cfg.name
        self._display_name = cfg.display_name
        self._sensor_type = cfg.sensor_type
        if not cfg.geometry.geometry_validated:
            _log.warning(
                "Toolhead %r has unvalidated (placeholder) geometry - workspace/well "
                "moves will be refused until it is measured, unless explicitly overridden.",
                name,
            )

    def clear_toolhead(self) -> None:
        """Physically remove the active toolhead: deactivate it and drop its mount record."""
        self._mounted_names.discard(self._name)
        self._toolhead = None
        self._name = ""
        self._display_name = ""
        self._sensor_type = None

    def set_mounted(self, mounted: bool) -> bool:
        """Record whether the *active* toolhead is physically installed.

        Args:
            mounted: True if the active toolhead is physically attached.

        Returns:
            True if this actually changed the mount state - the controller uses
            this to invalidate homing only on real hardware changes, so
            re-confirming an already-confirmed head (e.g. a script's
            mount_toolhead at startup) stays a harmless no-op.
            Always False when no toolhead is active.
        """
        if not self._name:
            return False
        if mounted == (self._name in self._mounted_names):
            return False
        if mounted:
            self._mounted_names.add(self._name)
        else:
            self._mounted_names.discard(self._name)
        return True

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
