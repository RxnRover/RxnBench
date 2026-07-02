"""Well plate geometry loader. YAML definitions live in rxn_bench_gantry/labware/."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_LABEL_RE = re.compile(r'^([A-Z])(\d+)$')
_DEFINITIONS_DIR = Path(__file__).parent / "labware"


@dataclass(frozen=True)
class PlateGeometry:
    """Uniform-spacing well plate geometry. All distances in mm from the plate corner."""

    rows: int
    columns: int
    spacing_mm: float
    well_diameter_mm: float
    well_depth_mm: float
    a1_offset_x: float
    a1_offset_y: float

    @property
    def well_count(self) -> int:
        return self.rows * self.columns

    def parse_label(self, label: str) -> tuple[int, int]:
        """Parse a well label into zero-based (row, column) indices.

        Args:
            label: Well label string, e.g. ``'A1'`` or ``'H12'``.

        Returns:
            Zero-based ``(row, col)`` tuple.

        Raises:
            ValueError: If the label format is invalid or the well is out of range.
        """
        m = _LABEL_RE.match(label.strip().upper())
        if not m:
            raise ValueError(
                f"Invalid well label {label!r}. Expected letter + number, e.g. 'A1'."
            )
        row = ord(m.group(1)) - ord('A')
        col = int(m.group(2)) - 1
        if not (0 <= row < self.rows and 0 <= col < self.columns):
            raise ValueError(
                f"Well {label!r} out of range for {self.rows}×{self.columns} plate."
            )
        return row, col

    def well_position(self, label: str) -> tuple[float, float]:
        """Return (x, y) centre of a well in mm, relative to the plate corner."""
        row, col = self.parse_label(label)
        x = self.a1_offset_x + col * self.spacing_mm
        y = self.a1_offset_y + row * self.spacing_mm
        return x, y

    @classmethod
    def from_yaml(cls, path: Path | str) -> PlateGeometry:
        """Load a PlateGeometry from a YAML file.

        Args:
            path: Path to the plate geometry YAML definition.

        Returns:
            Populated PlateGeometry instance.
        """
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            rows=data["rows"],
            columns=data["columns"],
            spacing_mm=data["spacing_mm"],
            well_diameter_mm=data["well_diameter_mm"],
            well_depth_mm=data["well_depth_mm"],
            a1_offset_x=data["a1_offset_x"],
            a1_offset_y=data["a1_offset_y"],
        )

    @classmethod
    def load(cls, name: str) -> PlateGeometry:
        """Load a plate geometry definition by name from the bundled labware directory.

        Args:
            name: Plate type name matching a YAML file under ``labware/``.

        Returns:
            Populated PlateGeometry instance.

        Raises:
            FileNotFoundError: If no matching definition file is found.
        """
        path = _DEFINITIONS_DIR / f"{name}.yaml"
        if not path.exists():
            available = cls.list_available()
            raise FileNotFoundError(
                f"No plate definition found for {name!r}. Available: {available}"
            )
        return cls.from_yaml(path)

    @classmethod
    def list_available(cls) -> list[str]:
        """Return names of all plate geometry YAML files in the labware directory."""
        if not _DEFINITIONS_DIR.exists():
            return []
        return sorted(p.stem for p in _DEFINITIONS_DIR.glob("*.yaml"))
