"""Owns the active workspace config and resolves well labels to absolute gantry XYZ coordinates."""
from __future__ import annotations

import logging
from pathlib import Path

from chem_bench_gantry.plate_geometry import PlateGeometry
from chem_bench_gantry.workspace_config import Orientation, WorkspaceConfig

_log = logging.getLogger(__name__)
_STATE_FILE = Path.home() / ".chem_bench" / "workspace.yaml"


class WorkspaceManager:

    def __init__(self) -> None:
        self._config: WorkspaceConfig | None = None
        self._geometry_cache: dict[str, PlateGeometry] = {}
        self._try_restore()

    @property
    def config(self) -> WorkspaceConfig | None:
        return self._config

    @property
    def name(self) -> str:
        return self._config.name if self._config else ""

    def load(self, name: str) -> None:
        self._config = WorkspaceConfig.load(name)
        self._geometry_cache.clear()
        self._save_state()

    def load_from_yaml(self, content: str) -> None:
        import yaml
        data = yaml.safe_load(content)
        self._config = WorkspaceConfig.from_dict(data)
        self._geometry_cache.clear()
        self._save_state()

    def clear(self) -> None:
        self._config = None
        self._geometry_cache.clear()
        _STATE_FILE.unlink(missing_ok=True)

    def _save_state(self) -> None:
        if self._config is None:
            return
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(self._config.to_yaml_string())
        except Exception as exc:
            _log.warning("Could not save workspace state: %s", exc)

    def _try_restore(self) -> None:
        if not _STATE_FILE.exists():
            return
        try:
            import yaml
            data = yaml.safe_load(_STATE_FILE.read_text())
            self._config = WorkspaceConfig.from_dict(data)
            _log.info("Restored workspace %r from %s", self._config.name, _STATE_FILE)
        except Exception as exc:
            _log.warning("Could not restore workspace state: %s", exc)

    def resolve_well(self, label: str) -> tuple[float, float, float]:
        if self._config is None:
            raise RuntimeError("No workspace loaded. Call load() or load_from_yaml() first.")

        plate_id, well_label = self._parse_label(label)
        plate = self._config.get_plate(plate_id)
        geom = self._load_geometry(plate.plate_type)

        plate_dx, plate_dy = geom.well_position(well_label)
        gantry_dx, gantry_dy = self._apply_orientation(plate_dx, plate_dy, plate.orientation)

        return (
            plate.origin_x + gantry_dx,
            plate.origin_y + gantry_dy,
            plate.origin_z,
        )

    def _parse_label(self, label: str) -> tuple[str, str]:
        if "/" in label:
            plate_id, well_label = label.split("/", 1)
            return plate_id.strip(), well_label.strip()
        if not self._config.plates:
            raise RuntimeError("Workspace has no plates.")
        return self._config.plates[0].id, label.strip()

    def _load_geometry(self, plate_type: str) -> PlateGeometry:
        if plate_type not in self._geometry_cache:
            self._geometry_cache[plate_type] = PlateGeometry.load(plate_type)
        return self._geometry_cache[plate_type]

    @staticmethod
    def _apply_orientation(
        plate_dx: float,
        plate_dy: float,
        orientation: Orientation,
    ) -> tuple[float, float]:
        if orientation is Orientation.STANDARD:
            return plate_dx, plate_dy
        if orientation is Orientation.ROTATED_90:
            return -plate_dy, plate_dx
        raise ValueError(f"Unknown orientation: {orientation!r}")

    @staticmethod
    def list_available() -> list[str]:
        return WorkspaceConfig.list_available()
