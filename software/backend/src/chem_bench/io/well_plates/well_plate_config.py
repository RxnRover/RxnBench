"""
Well plate geometry config - loaded from a per-plate YAML file.

Provides physical dimensions, well layout, and helper methods for
computing individual well positions. Designed to mirror the ToolheadConfig
pattern so plates can be swapped in the same way as toolheads.

Author: John Brittain
Date: Jun 18 2026
"""
import yaml
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WellLayout:
    """Row/column count of the plate."""
    rows: int       # A=0 … H=7 for a 96-well plate
    columns: int    # 1-based column count


@dataclass
class PlateDimensions:
    """Outer physical dimensions of the plate in mm."""
    length: float   # long axis (X direction when loaded front-to-back)
    width: float    # short axis (Y direction)
    height: float   # plate height (used for Z clearance calculations)


@dataclass
class WellGeometry:
    """Geometry of an individual well."""
    diameter: float     # inner diameter, mm
    depth: float        # well depth, mm
    volume_ul: float    # nominal volume, µL


@dataclass
class WellSpacing:
    """Center-to-center distance between adjacent wells in mm."""
    row_spacing: float      # Y direction (row A→B→…)
    col_spacing: float      # X direction (col 1→2→…)


@dataclass
class WellOrigin:
    """Position of well A1 center relative to the plate's bottom-left corner in mm."""
    x: float
    y: float


@dataclass
class WellPlateConfig:
    """Complete config for a well plate, loaded from a YAML file.

    Attributes
    ----------
    name : str
        Internal name, matches the YAML filename (e.g. '96_well_standard').
    display_name : str
        Human-readable name shown in UIs.
    layout : WellLayout
    dimensions : PlateDimensions
    well : WellGeometry
    spacing : WellSpacing
    origin : WellOrigin
        Position of well A1 relative to the plate corner.
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

    def well_position(self, row: int, col: int) -> tuple[float, float]:
        """Return (x, y) center of well (row, col) relative to plate corner.

        row and col are 0-indexed (row 0 = row A, col 0 = column 1).
        """
        x = self.origin.x + col * self.spacing.col_spacing
        y = self.origin.y + row * self.spacing.row_spacing
        return x, y

    def well_label(self, row: int, col: int) -> str:
        """Return the standard alphanumeric label, e.g. 'A1', 'H12'."""
        return f"{chr(ord('A') + row)}{col + 1}"

    @classmethod
    def from_yaml(cls, path: "Path | str") -> "WellPlateConfig":
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
    def load(cls, name: str) -> "WellPlateConfig":
        """Load a config by plate name from the default directory."""
        path = Path(__file__).parent / name / f"{name}.yaml"
        return cls.from_yaml(path)
