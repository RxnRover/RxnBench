"""Well plate geometry loader. YAML definitions live in rxn_bench_gantry/labware/."""
from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_LABEL_RE = re.compile(r'^([A-Z])(\d+)$')
_DEFINITIONS_DIR = Path(__file__).parent / "labware"
_log = logging.getLogger(__name__)

_REQUIRED_FIELDS = (
    "rows", "columns",
    "well_diameter_mm", "well_depth_mm", "plate_height_mm",
    "a1_offset_x", "a1_offset_y",
)

# standard microplate footprint, used when a definition omits it.
_SBS_WIDTH_MM = 127.76
_SBS_HEIGHT_MM = 85.48


@dataclass(frozen=True)
class PlateGeometry:
    """Uniform-spacing well plate geometry. All distances in mm from the plate corner."""

    rows: int
    columns: int
    well_diameter_mm: float
    well_depth_mm: float
    plate_height_mm: float  # deck to plate top surface - what travel moves must clear
    a1_offset_x: float
    a1_offset_y: float
    spacing_mm: float | None = None    # centre-to-centre, both axes; used when x/y not given
    spacing_mm_x: float | None = None  # centre-to-centre along columns; overrides spacing_mm
    spacing_mm_y: float | None = None  # centre-to-centre along rows; overrides spacing_mm
    width_mm: float = _SBS_WIDTH_MM    # plate footprint along X
    height_mm: float = _SBS_HEIGHT_MM  # plate footprint along Y

    def __post_init__(self) -> None:
        if self.spacing_mm is None and (self.spacing_mm_x is None or self.spacing_mm_y is None):
            raise ValueError(
                "Labware definition needs either 'spacing_mm' or both "
                "'spacing_mm_x' and 'spacing_mm_y'."
            )

    @property
    def well_count(self) -> int:
        return self.rows * self.columns

    @property
    def effective_spacing_x(self) -> float:
        return self.spacing_mm_x if self.spacing_mm_x is not None else self.spacing_mm

    @property
    def effective_spacing_y(self) -> float:
        return self.spacing_mm_y if self.spacing_mm_y is not None else self.spacing_mm

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
        x = self.a1_offset_x + col * self.effective_spacing_x
        y = self.a1_offset_y + row * self.effective_spacing_y
        return x, y

    @classmethod
    def from_yaml(cls, path: Path | str) -> PlateGeometry:
        """Load a PlateGeometry from a YAML file.

        Args:
            path: Path to the plate geometry YAML definition.

        Returns:
            Populated PlateGeometry instance.

        Raises:
            ValueError: If the file is empty, not a mapping, or missing
                required geometry fields - the message names the file and
                the fields so a half-written definition is easy to finish.
        """
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(
                f"Labware definition {path} is empty or not a YAML mapping. "
                f"Required fields: {', '.join(_REQUIRED_FIELDS)}."
            )
        missing = [k for k in _REQUIRED_FIELDS if k not in data]
        if missing:
            raise ValueError(
                f"Labware definition {path} is missing required fields: "
                f"{', '.join(missing)}."
            )
        return cls(
            rows=data["rows"],
            columns=data["columns"],
            well_diameter_mm=data["well_diameter_mm"],
            well_depth_mm=data["well_depth_mm"],
            plate_height_mm=data["plate_height_mm"],
            a1_offset_x=data["a1_offset_x"],
            a1_offset_y=data["a1_offset_y"],
            spacing_mm=data.get("spacing_mm"),
            spacing_mm_x=data.get("spacing_mm_x"),
            spacing_mm_y=data.get("spacing_mm_y"),
            width_mm=data.get("width_mm", _SBS_WIDTH_MM),
            height_mm=data.get("height_mm", _SBS_HEIGHT_MM),
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

    @classmethod
    def dump_all_yaml(cls) -> str:
        """Serialise every valid bundled labware definition to one YAML document.

        Definitions that fail to load (empty file, missing fields) are skipped
        with a logged warning so one half-written labware file cannot take down
        GetLabware - and with it the deck canvas and get_workspace_wells() -
        for every other plate type. Explicitly loading the bad plate type
        (PlateGeometry.load / a workspace that uses it) still raises.

        Returns:
            YAML string mapping plate type name to its geometry fields. This is
            the single source of truth the frontend canvas and experiment client
            fetch over SiLA instead of hardcoding plate dimensions.
        """
        result: dict[str, dict] = {}
        for name in cls.list_available():
            try:
                result[name] = dataclasses.asdict(cls.load(name))
            except Exception as exc:
                _log.warning("Skipping labware definition %r: %s", name, exc)
        return yaml.safe_dump(result, default_flow_style=False, sort_keys=True)
