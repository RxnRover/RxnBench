"""Workspace definition - which plates are on the deck and where."""
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
    """A plate type placed at a specific position and orientation on the deck."""

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
        """Return the PlacedPlate with the given ID.

        Args:
            plate_id: The plate identifier string.

        Returns:
            The matching PlacedPlate.

        Raises:
            KeyError: If no plate with that ID exists in this workspace.
        """
        for p in self.plates:
            if p.id == plate_id:
                return p
        available = [p.id for p in self.plates]
        raise KeyError(f"Plate {plate_id!r} not in workspace. Available: {available}")

    @classmethod
    def from_dict(cls, data: dict) -> WorkspaceConfig:
        """Construct a WorkspaceConfig from a parsed YAML dict.

        Args:
            data: Dict with ``name``, ``calibration_reference_well``, and ``plates`` keys.

        Returns:
            Populated WorkspaceConfig instance.
        """
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
        """Load a WorkspaceConfig from a YAML file.

        Args:
            path: Path to the workspace YAML definition file.

        Returns:
            Populated WorkspaceConfig instance.
        """
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def load(cls, name: str) -> WorkspaceConfig:
        """Load a workspace definition by name from the bundled definitions directory.

        Args:
            name: Workspace name matching a file in ``workspace/definitions/``.

        Returns:
            Populated WorkspaceConfig instance.

        Raises:
            FileNotFoundError: If no matching definition file is found.
        """
        path = _DEFINITIONS_DIR / f"{name}.yaml"
        if not path.exists():
            available = cls.list_available()
            raise FileNotFoundError(
                f"No workspace definition found for {name!r}. Available: {available}"
            )
        return cls.from_yaml(path)

    def to_yaml_string(self) -> str:
        """Serialise this workspace config to a YAML string.

        Returns:
            YAML representation of the workspace, suitable for writing to a file.
        """
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
        """Return names of all workspace YAML files in the definitions directory."""
        if not _DEFINITIONS_DIR.exists():
            return []
        return sorted(p.stem for p in _DEFINITIONS_DIR.glob("*.yaml")
                      if not p.name.startswith("_"))
