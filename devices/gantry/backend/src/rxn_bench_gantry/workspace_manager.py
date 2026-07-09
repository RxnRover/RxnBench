"""Owns the active workspace config and resolves well labels to absolute gantry XYZ."""
from __future__ import annotations

import logging
from pathlib import Path

from rxn_bench_gantry.plate_geometry import PlateGeometry
from rxn_bench_gantry.workspace_config import Orientation, OriginMode, PlacedPlate, WorkspaceConfig

_log = logging.getLogger(__name__)
_STATE_FILE = Path.home() / ".rxn_bench" / "workspace.yaml"


class WorkspaceManager:
    """Loads and persists the active workspace; resolves 'plate_id/well_label' → gantry XYZ."""

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

    def to_yaml(self) -> str:
        """Return the active workspace as a YAML string, or empty string if none is loaded."""
        return self._config.to_yaml_string() if self._config else ""

    def load(self, name: str) -> None:
        """Load a workspace by name from the bundled definitions directory and persist it.

        Args:
            name: Workspace name matching a file in ``workspace/definitions/``.
        """
        self._config = WorkspaceConfig.load(name)
        self._geometry_cache.clear()
        self._save_state()

    def load_from_yaml(self, content: str) -> None:
        """Load a workspace from a raw YAML string and persist it.

        Args:
            content: Full YAML content of a workspace definition.
        """
        import yaml
        data = yaml.safe_load(content)
        self._config = WorkspaceConfig.from_dict(data)
        self._geometry_cache.clear()
        self._save_state()

    def clear(self) -> None:
        """Unload the active workspace and delete the persisted state file."""
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
        """Resolve a well label to the absolute gantry XYZ of that well's opening.

        Args:
            label: Well label of the form ``'plate_id/well_label'`` (e.g. ``'plate1/A3'``),
                or just ``'well_label'`` to use the first plate in the workspace.

        Returns:
            Tuple of ``(x, y, z)`` in mm in the gantry coordinate frame. ``z``
            is the plate's *top surface* (``origin_z + plate_height_mm``) -
            the well's opening, not its bottom - since that is the physically
            meaningful height to dock at before any tool-specific engagement
            depth is applied on top of it.

        Raises:
            RuntimeError: If no workspace is loaded.
            KeyError: If the plate ID is not found in the current workspace.
            ValueError: If the well label format or row/column index is invalid.
        """
        plate, geom, well_label = self._resolve_plate(label)

        plate_dx, plate_dy = geom.well_position(well_label)
        if plate.origin_mode is OriginMode.CENTER:
            # origin is the centre of the plate's footprint, not its corner, so
            # rotation pivots in place instead of swinging the footprint out to
            # a different quadrant of the deck.
            plate_dx -= geom.width_mm / 2
            plate_dy -= geom.height_mm / 2
        # else CORNER: origin is the plate's un-rotated corner, so rotation
        # pivots around that corner and the footprint swings into the
        # adjacent quadrant - the caller is responsible for leaving room.
        gantry_dx, gantry_dy = self._apply_orientation(plate_dx, plate_dy, plate.orientation)

        return (
            plate.origin_x + gantry_dx,
            plate.origin_y + gantry_dy,
            plate.origin_z + geom.plate_height_mm,
        )

    def get_well_depth(self, label: str) -> float:
        """Return the specific well's depth in mm (top surface to well bottom).

        Used to bounds-check a toolhead's configured engagement depth
        (``z_engage``) against the well it is about to be sent into, so a
        toolhead calibrated for a deep-well plate doesn't punch through the
        bottom of a shallower one.

        Args:
            label: Well label, same format as :meth:`resolve_well`.

        Raises:
            RuntimeError: If no workspace is loaded.
            KeyError: If the plate ID is not found in the current workspace.
        """
        _plate, geom, _well_label = self._resolve_plate(label)
        return geom.well_depth_mm

    def _resolve_plate(self, label: str) -> tuple[PlacedPlate, PlateGeometry, str]:
        if self._config is None:
            raise RuntimeError("No workspace loaded. Call load() or load_from_yaml() first.")
        plate_id, well_label = self._parse_label(label)
        plate = self._config.get_plate(plate_id)
        geom = self._load_geometry(plate.plate_type)
        return plate, geom, well_label

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

    def max_labware_top_z(self) -> float:
        """Return the highest loaded labware top surface (origin_z + plate_height_mm) in mm.

        Used to size safe clearance-travel height from the actual deck
        contents instead of a fixed guess. A plate whose type can't be
        loaded is skipped (with a warning) rather than failing the whole
        calculation - the same resilience GetLabware already applies to a
        single bad definition file.

        Returns:
            The tallest placed plate's top-surface height in mm, or 0.0 if
            no workspace is loaded or it has no plates.
        """
        if self._config is None or not self._config.plates:
            return 0.0
        tops = []
        for plate in self._config.plates:
            try:
                geom = self._load_geometry(plate.plate_type)
            except Exception as exc:
                _log.warning("Skipping plate %r in clearance calc: %s", plate.id, exc)
                continue
            tops.append(plate.origin_z + geom.plate_height_mm)
        return max(tops) if tops else 0.0

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
        """Return names of all available workspace definition files."""
        return WorkspaceConfig.list_available()
