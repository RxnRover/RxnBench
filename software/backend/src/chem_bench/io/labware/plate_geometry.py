"""
Plate geometry — uniform-spacing model for ANSI/SLAS standard well plates.

A single spacing_mm covers both axes, which holds for every current SLAS
standard (96, 384, 24-well).

YAML definition format (see definitions/96_well_standard.yaml for an example):

    rows: 8
    columns: 12
    spacing_mm: 9.0
    well_diameter_mm: 6.94
    well_depth_mm: 10.67
    a1_offset_x: 14.38   # mm from plate corner to A1 centre, X
    a1_offset_y: 11.24   # mm from plate corner to A1 centre, Y

Author: John Brittain
Date: Jun 2026
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_LABEL_RE = re.compile(r'^([A-Z])(\d+)$')
_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


@dataclass(frozen=True)
class PlateGeometry:
    """Uniform-spacing well plate geometry.

    All offsets are in mm and measured from the plate's bottom-left corner.
    Rows are 0-indexed (0 = A). Columns are 0-indexed (0 = column 1).
    """
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
        """Parse a well label (e.g. 'A1', 'H12') into 0-indexed (row, col).

        Raises ValueError if malformed or out of range for this plate.
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
        """Return (x, y) centre of a well in mm, relative to the plate corner.

        Raises ValueError if the label is malformed or out of range.
        """
        row, col = self.parse_label(label)
        x = self.a1_offset_x + col * self.spacing_mm
        y = self.a1_offset_y + row * self.spacing_mm
        return x, y

    @classmethod
    def from_yaml(cls, path: Path | str) -> PlateGeometry:
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
        """Load a plate by name from the bundled definitions directory.

        Raises FileNotFoundError if the definition does not exist.
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
        if not _DEFINITIONS_DIR.exists():
            return []
        return sorted(p.stem for p in _DEFINITIONS_DIR.glob("*.yaml"))
