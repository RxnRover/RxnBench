"""Toolhead geometry dataclasses and YAML config loader."""
import yaml
from dataclasses import dataclass
from pathlib import Path

_TOOLHEADS_DIR = Path(__file__).parent / "toolheads"


@dataclass
class ToolheadGeometry:
    """Physical dimensions and offsets for one toolhead, all in mm."""

    footprint_x: float
    footprint_y: float
    offset_x: float
    offset_y: float
    tip_offset_z: float
    z_engage: float
    tip_x: float = 0.0
    tip_y: float = 0.0
    geometry_validated: bool = True  # False = placeholder, not yet measured
    calibrated_at: str = ""  # ISO timestamp of the last calibration wizard run, "" if never


@dataclass
class ToolheadConfig:
    """Full toolhead configuration loaded from a YAML file."""

    name: str
    display_name: str
    geometry: ToolheadGeometry
    sensor_type: str | None = None

    @classmethod
    def from_yaml(cls, path: Path | str) -> 'ToolheadConfig':
        """Load a ToolheadConfig from a YAML file.

        Args:
            path: Path to the toolhead YAML file.

        Returns:
            Populated ToolheadConfig instance.
        """
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
                geometry_validated=geom_data.get('geometry_validated', True),
            ),
        )

    @classmethod
    def load(cls, name: str) -> 'ToolheadConfig':
        """Load a config by toolhead name from the bundled toolheads directory."""
        path = _TOOLHEADS_DIR / name / f'{name}_toolhead.yaml'
        return cls.from_yaml(path)
