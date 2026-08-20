"""OrcaSlicerに依存しない3D穴検出I/F。"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, TypeAlias

from .config import HoleReinforcementConfig


Vector3: TypeAlias = tuple[float, float, float]
Triangle: TypeAlias = tuple[int, int, int]


class HoleShape(Enum):
    CIRCLE = "circle"
    HEXAGON = "hexagon"
    OCTAGON = "octagon"
    REGULAR_POLYGON = "regular_polygon"


class HoleEndKind(Enum):
    THROUGH = "through"
    BLIND = "blind"


@dataclass(frozen=True, slots=True)
class MeshSnapshot:
    vertices_mm: tuple[Vector3, ...]
    triangles: tuple[Triangle, ...]


@dataclass(frozen=True, slots=True)
class CylindricalHoleCandidate:
    center_mm: Vector3
    axis: Vector3
    radius_mm: float
    depth_mm: float
    axial_start_mm: float
    axial_end_mm: float
    confidence: float
    triangle_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PolygonalHoleCandidate:
    shape: HoleShape
    side_count: int
    center_mm: Vector3
    axis: Vector3
    cross_section_mm: tuple[Vector3, ...]
    across_flats_mm: float
    depth_mm: float
    axial_start_mm: float
    axial_end_mm: float
    confidence: float
    triangle_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DetectedHole:
    shape: HoleShape
    end_kind: HoleEndKind
    center_mm: Vector3
    axis: Vector3
    diameter_mm: float
    depth_mm: float
    confidence: float


class HoleDetector(Protocol):
    def detect(
        self,
        mesh: MeshSnapshot,
        config: HoleReinforcementConfig,
    ) -> Sequence[DetectedHole]: ...
