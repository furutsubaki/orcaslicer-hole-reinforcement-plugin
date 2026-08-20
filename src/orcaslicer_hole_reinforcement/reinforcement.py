"""OrcaSlicerに依存しない2D補強計画I/F。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from .config import HoleReinforcementConfig
from .detection import DetectedHole


Point2: TypeAlias = tuple[float, float]
Polygon2: TypeAlias = tuple[Point2, ...]


@dataclass(frozen=True, slots=True)
class LayerPlane:
    index: int
    print_z_mm: float


@dataclass(frozen=True, slots=True)
class ReinforcementRegion:
    layer_index: int
    contours_mm: tuple[Polygon2, ...]


class ReinforcementPlanner(Protocol):
    def plan(
        self,
        holes: Sequence[DetectedHole],
        layers: Sequence[LayerPlane],
        config: HoleReinforcementConfig,
    ) -> Sequence[ReinforcementRegion]: ...
