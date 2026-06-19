"""
Laboratory well plate data model.

Pure geometry — no hardware, no UI, no I/O dependencies.
Loaded from per-plate YAML definitions in labware/definitions/.

Author: John Brittain
Date: Jun 18 2026
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml


@dataclass(frozen=True)
class WellLayout:
    rows: int       # A=0 … last row = rows-1
    columns: int    # 1-based in labels, 0-based internally


@dataclass(frozen=True)
class PlateDimensions:
    length: float   # mm, long axis (X direction)
    width: float    # mm, short axis (Y direction)
    height: float   # mm, total plate height


@dataclass(frozen=True)
class WellGeometry:
    diameter: float    # mm, inner well diameter
    depth: float       # mm, well depth from top surface
    volume_ul: float   # µL, nominal working volume


@dataclass(frozen=True)
class WellSpacing:
    row_spacing: float  # mm, center-to-center between adjacent rows (Y axis)
    col_spacing: float  # mm, center-to-center between adjacent columns (X axis)


@dataclass(frozen=True)
class WellOrigin:
    """Center of well A1 relative to the plate's bottom-left corner, in mm."""
    x: float
    y: float


_LABEL_RE = re.compile(r'^([A-Z])(\d+)$')
_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


@dataclass(frozen=True)
class WellPlate:
    """Well plate geometry and coordinate model.

    All positions are relative to the plate's bottom-left corner (mm).
    Rows are 0-indexed (row 0 = A). Columns are 0-indexed (col 0 = column 1).
    """
    name: str
    display_name: str
    layout: WellLayout
    dimensions: PlateDimensions
    well: WellGeometry
    spacing: WellSpacing
    origin: WellOrigin

    @property
    def well_count(self) -> int:
        return self.layout.rows * self.layout.columns

    @property
    def row_count(self) -> int:
        return self.layout.rows

    @property
    def column_count(self) -> int:
        return self.layout.columns

    def is_valid(self, row: int, col: int) -> bool:
        """Return True if (row, col) is within the plate bounds."""
        return 0 <= row < self.layout.rows and 0 <= col < self.layout.columns

    def well_label(self, row: int, col: int) -> str:
        """Return the alphanumeric label for a well, e.g. 'A1', 'H12'.

        Raises ValueError if (row, col) is out of range.
        """
        if not self.is_valid(row, col):
            raise ValueError(
                f"Well ({row}, {col}) out of range for {self.name!r} "
                f"({self.layout.rows} rows × {self.layout.columns} cols)"
            )
        return f"{chr(ord('A') + row)}{col + 1}"

    def parse_label(self, label: str) -> tuple[int, int]:
        """Parse a well label such as 'A3' into 0-indexed (row, col).

        Raises ValueError if the label is malformed or out of range for this plate.
        """
        match = _LABEL_RE.match(label.strip().upper())
        if not match:
            raise ValueError(
                f"Invalid well label {label!r}. Expected format: letter + number, e.g. 'A1', 'H12'."
            )
        row = ord(match.group(1)) - ord('A')
        col = int(match.group(2)) - 1  # 1-based label → 0-based index
        if not self.is_valid(row, col):
            raise ValueError(
                f"Well {label!r} out of range for {self.name!r} "
                f"({self.layout.rows} rows × {self.layout.columns} cols)"
            )
        return row, col

    def well_position(self, row: int, col: int) -> tuple[float, float]:
        """Return (x, y) center of a well in mm, relative to the plate corner.

        Raises ValueError if (row, col) is out of range.
        """
        if not self.is_valid(row, col):
            raise ValueError(
                f"Well ({row}, {col}) out of range for {self.name!r}"
            )
        x = self.origin.x + col * self.spacing.col_spacing
        y = self.origin.y + row * self.spacing.row_spacing
        return x, y

    def well_position_by_label(self, label: str) -> tuple[float, float]:
        """Return (x, y) center of a well in mm, looked up by label ('A3', 'H12', …).

        Raises ValueError if the label is malformed or out of range.
        """
        row, col = self.parse_label(label)
        return self.well_position(row, col)

    def wells(self) -> Iterator[tuple[int, int]]:
        """Yield all (row, col) pairs in row-major order: A1, A2, …, B1, B2, …"""
        for row in range(self.layout.rows):
            for col in range(self.layout.columns):
                yield row, col

    @classmethod
    def from_yaml(cls, path: Path | str) -> WellPlate:
        """Load a WellPlate from a YAML file at the given path."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            name=data["name"],
            display_name=data["display_name"],
            layout=WellLayout(**data["layout"]),
            dimensions=PlateDimensions(**data["dimensions"]),
            well=WellGeometry(**data["well"]),
            spacing=WellSpacing(**data["spacing"]),
            origin=WellOrigin(**data["origin"]),
        )

    @classmethod
    def load(cls, name: str) -> WellPlate:
        """Load a plate by name from the bundled definitions directory.

        Looks for definitions/<name>/<name>.yaml relative to this file.
        Raises FileNotFoundError if the definition does not exist.
        """
        path = _DEFINITIONS_DIR / name / f"{name}.yaml"
        if not path.exists():
            available = cls.list_available()
            raise FileNotFoundError(
                f"No labware definition found for {name!r}. "
                f"Available: {available}"
            )
        return cls.from_yaml(path)

    @classmethod
    def list_available(cls) -> list[str]:
        """Return sorted names of all available plate definitions."""
        if not _DEFINITIONS_DIR.exists():
            return []
        return sorted(
            d.name for d in _DEFINITIONS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
        )
