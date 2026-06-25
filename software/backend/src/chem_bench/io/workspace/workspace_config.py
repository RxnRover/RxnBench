"""
Workspace configuration — describes which plates are on the deck and where.

YAML format (see definitions/workspace_template.yaml for a full example):

    name: my_workspace
    calibration_reference_well: reagents/A1

    plates:
      - id: reagents
        plate_type: 96_well_standard
        origin:
          x: 50.0
          y: 30.0
          z: 15.0
        orientation: standard   # or rotated_90

Author: John Brittain
Date: Jun 2026
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


class Orientation(str, Enum):
    STANDARD = "standard"
    ROTATED_90 = "rotated_90"


@dataclass(frozen=True)
class PlacedPlate:
    """A single plate registered on the deck."""
    id: str
    plate_type: str
    origin_x: float
    origin_y: float
    origin_z: float
    orientation: Orientation = Orientation.STANDARD


@dataclass(frozen=True)
class WorkspaceConfig:
    """Full description of the active workspace — all plates, positions, and orientations."""
    name: str
    calibration_reference_well: str
    plates: tuple[PlacedPlate, ...]

    def get_plate(self, plate_id: str) -> PlacedPlate:
        """Return the placed plate with the given id.

        Raises KeyError if not found.
        """
        for p in self.plates:
            if p.id == plate_id:
                return p
        available = [p.id for p in self.plates]
        raise KeyError(f"Plate {plate_id!r} not in workspace. Available: {available}")

    @classmethod
    def from_dict(cls, data: dict) -> WorkspaceConfig:
        """Build a WorkspaceConfig from an already-parsed YAML dict."""
        plates: list[PlacedPlate] = []
        for entry in data.get("plates", []):
            origin = entry["origin"]
            plates.append(PlacedPlate(
                id=entry["id"],
                plate_type=entry["plate_type"],
                origin_x=float(origin["x"]),
                origin_y=float(origin["y"]),
                origin_z=float(origin["z"]),
                orientation=Orientation(entry.get("orientation", "standard")),
            ))
        return cls(
            name=data["name"],
            calibration_reference_well=data["calibration_reference_well"],
            plates=tuple(plates),
        )

    @classmethod
    def from_yaml(cls, path: Path | str) -> WorkspaceConfig:
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def load(cls, name: str) -> WorkspaceConfig:
        """Load a workspace by name from the bundled definitions directory.

        Raises FileNotFoundError if the definition does not exist.
        """
        path = _DEFINITIONS_DIR / f"{name}.yaml"
        if not path.exists():
            available = cls.list_available()
            raise FileNotFoundError(
                f"No workspace definition found for {name!r}. Available: {available}"
            )
        return cls.from_yaml(path)

    @classmethod
    def list_available(cls) -> list[str]:
        if not _DEFINITIONS_DIR.exists():
            return []
        return sorted(p.stem for p in _DEFINITIONS_DIR.glob("*.yaml")
                      if not p.name.startswith("_"))
