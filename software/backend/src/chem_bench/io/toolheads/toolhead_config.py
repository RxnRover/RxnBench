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
        Body centre offset from the carriage mount point.
        Used by move_to() to position the body over a target.
    tip_x, tip_y : float
        Tip position relative to the body centre.
        The actual sensing/dispensing point used for XY positioning.
        Defaults to (0, 0) — tip at body centre.
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
    tip_x: float = 0.0
    tip_y: float = 0.0
    requires_manual_z: bool = True
    requires_manual_homing: bool = False


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
    sensor_type : str | None
        Optional key into the sensor_registry (e.g. 'ph').
        Lives here, not on ToolheadGeometry, because it describes what device
        is attached, not the toolhead's physical shape.
    """
    name: str
    display_name: str
    geometry: ToolheadGeometry
    sensor_type: str | None = None

    @classmethod
    def from_yaml(cls, path: Path | str) -> 'ToolheadConfig':
        with open(path) as f:
            data = yaml.safe_load(f)
        geom_data = data['geometry']
        return cls(
            name=data['name'],
            display_name=data['display_name'],
            sensor_type=data.get('sensor_type'),
            geometry=ToolheadGeometry(
                footprint_x=geom_data['footprint_x'],
                footprint_y=geom_data['footprint_y'],
                offset_x=geom_data['offset_x'],
                offset_y=geom_data['offset_y'],
                tip_offset_z=geom_data['tip_offset_z'],
                z_engage=geom_data['z_engage'],
                tip_x=geom_data.get('tip_x', 0.0),
                tip_y=geom_data.get('tip_y', 0.0),
                requires_manual_z=geom_data.get('requires_manual_z', True),
                requires_manual_homing=geom_data.get('requires_manual_homing', False),
            ),
        )

    @classmethod
    def load(cls, name: str) -> 'ToolheadConfig':
        """Load a config by toolhead name from the default directory."""
        path = Path(__file__).parent / name / f'{name}_toolhead.yaml'
        return cls.from_yaml(path)
