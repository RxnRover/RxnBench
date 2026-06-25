"""
Workspace manager — owns the active workspace config and resolves well labels
to absolute gantry XYZ coordinates.

The primary workflow is:
  1. Create a workspace YAML (see io/workspace/definitions/_workspace_template.yaml).
  2. Either copy it to io/workspace/definitions/ and call load(name), or send the
     raw YAML content from the frontend via load_from_yaml(content).
  3. Call resolve_well(label) to get the world-space XY(Z) of any well.
     GantryController.move_to() applies toolhead offset compensation on top.

Orientation conventions
-----------------------
standard:    X increases with column (1→12), Y increases with row (A→H).
rotated_90:  90° CCW rotation of the plate on the deck:
               gantry_dx = -plate_dy
               gantry_dy =  plate_dx

Author: John Brittain
Date: Jun 2026
"""
from __future__ import annotations

from chem_bench.io.labware.plate_geometry import PlateGeometry
from chem_bench.io.workspace.workspace_config import Orientation, WorkspaceConfig


class WorkspaceManager:

    def __init__(self) -> None:
        self._config: WorkspaceConfig | None = None
        self._geometry_cache: dict[str, PlateGeometry] = {}

    @property
    def config(self) -> WorkspaceConfig | None:
        return self._config

    @property
    def name(self) -> str:
        return self._config.name if self._config else ""

    def load(self, name: str) -> None:
        """Load a workspace by name from the bundled definitions directory."""
        self._config = WorkspaceConfig.load(name)
        self._geometry_cache.clear()

    def load_from_yaml(self, content: str) -> None:
        """Load a workspace from raw YAML content (e.g. sent from the frontend over SiLA)."""
        import yaml
        data = yaml.safe_load(content)
        self._config = WorkspaceConfig.from_dict(data)
        self._geometry_cache.clear()

    def clear(self) -> None:
        self._config = None
        self._geometry_cache.clear()

    def resolve_well(self, label: str) -> tuple[float, float, float]:
        """Translate a well label to world-space (X, Y, Z) in mm.

        Accepts:
            "A1"        — resolves against the first plate in the workspace.
            "plate1/A1" — resolves against the named plate.

        Returns world-space well-centre coordinates.  Toolhead offset
        compensation is applied by GantryController.move_to(), not here.

        Raises:
            RuntimeError      — no workspace loaded.
            KeyError          — plate id not found.
            ValueError        — well label malformed or out of range.
            FileNotFoundError — plate_type definition not installed.
        """
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
