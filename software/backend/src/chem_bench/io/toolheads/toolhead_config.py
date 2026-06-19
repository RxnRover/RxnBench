"""
Toolhead geometry config - loaded from a per-toolhead YAML file and used
by the motion platform to apply the correct offsets, check bounds, and placement when moving.

Author: John Brittain
Date: Jun 11 2026
"""
import yaml
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolheadGeometry:
    """Physical offsets for a toolhead, all in mm.

    Attributes
    ----------
    footprint_x, footprint_y : float
        Physical size of the toolhead body in XY.
    offset_x, offset_y : float
        Tool center offset from the carriage mount point.
    tip_offset_z : float
        Distance the tool tip hangs below the carriage mount point.
        Used to compute the effective minimum safe carriage Z.
    z_engage : float
        How far down the tool goes when working.
    """
    footprint_x: float
    footprint_y: float
    offset_x: float
    offset_y: float
    tip_offset_z: float
    z_engage: float


@dataclass
class ToolheadConfig:
    """Full config for a toolhead, loaded from a YAML file.

    Attributes
    ----------
    name : str
        Internal name, matches the YAML filename.
    display_name : str
        Human-readable name shown in UIs.
    geometry : ToolheadGeometry
    """
    name: str
    display_name: str
    geometry: ToolheadGeometry

    @classmethod
    def from_yaml(cls, path: Path | str) -> 'ToolheadConfig':
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            name=data['name'],
            display_name=data['display_name'],
            geometry=ToolheadGeometry(**data['geometry']),
        )

    @classmethod
    def load(cls, name: str) -> 'ToolheadConfig':
        """Load a config by toolhead name from the default directory."""
        path = Path(__file__).parent / name / f'{name}_toolhead.yaml'
        return cls.from_yaml(path)
