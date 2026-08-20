"""形状検出器を統合し、同じ内壁の候補を一意にする。"""

from collections.abc import Callable
from typing import TypeAlias

from .config import HoleReinforcementConfig
from .cylinder_detection import CylindricalHoleDetector
from .detection import CylindricalHoleCandidate, MeshSnapshot, PolygonalHoleCandidate
from .polygon_detection import PolygonalHoleDetector


HoleCandidate: TypeAlias = CylindricalHoleCandidate | PolygonalHoleCandidate


class HoleCandidateDetector:
    def detect(
        self,
        mesh: MeshSnapshot,
        config: HoleReinforcementConfig,
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> tuple[HoleCandidate, ...]:
        polygons = PolygonalHoleDetector().detect(
            mesh, config, cancelled=cancelled
        )
        polygon_triangles = {
            triangle for candidate in polygons for triangle in candidate.triangle_indices
        }
        cylinders = tuple(
            candidate
            for candidate in CylindricalHoleDetector().detect(
                mesh, config, cancelled=cancelled
            )
            if polygon_triangles.isdisjoint(candidate.triangle_indices)
        )
        return (*polygons, *cylinders)
