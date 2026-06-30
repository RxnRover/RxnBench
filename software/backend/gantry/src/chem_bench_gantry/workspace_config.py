"""Workspace config — which plates are on the deck and where. YAML definitions in workspace/definitions/."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

_DEFINITIONS_DIR = Path(__file__).parent / "workspace" / "definitions"


class Orientation(str, Enum):
    STANDARD = "standard"
    ROTATED_90 = "rotated_90"


@dataclass(frozen=True)
class PlacedPlate:
    id: str
    plate_type: str
    origin_x: float
    origin_y: float
    origin_z: float
    orientation: Orientation = Orientation.STANDARD


@dataclass(frozen=True)
class WorkspaceConfig:
    """Full description of the active workspace - all plates, positions, orientations."""
    name: str
    calibration_reference_well: str
    plates: tuple[PlacedPlate, ...]

    def get_plate(self, plate_id: str) -> PlacedPlate:
        for p in self.plates:
            if p.id == plate_id:
                return p
        available = [p.id for p in self.plates]
        raise KeyError(f"Plate {plate_id!r} not in workspace. Available: {available}")

    @classmethod
    def from_dict(cls, data: dict) -> WorkspaceConfig:
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
        path = _DEFINITIONS_DIR / f"{name}.yaml"
        if not path.exists():
            available = cls.list_available()
            raise FileNotFoundError(
                f"No workspace definition found for {name!r}. Available: {available}"
            )
        return cls.from_yaml(path)

    def to_yaml_string(self) -> str:
        data = {
            "name": self.name,
            "calibration_reference_well": self.calibration_reference_well,
            "plates": [
                {
                    "id": p.id,
                    "plate_type": p.plate_type,
                    "origin": {"x": p.origin_x, "y": p.origin_y, "z": p.origin_z},
                    "orientation": p.orientation.value,
                }
                for p in self.plates
            ],
        }
        return yaml.dump(data, default_flow_style=False)

    @classmethod
    def list_available(cls) -> list[str]:
        if not _DEFINITIONS_DIR.exists():
            return []
        return sorted(p.stem for p in _DEFINITIONS_DIR.glob("*.yaml")
                      if not p.name.startswith("_"))
