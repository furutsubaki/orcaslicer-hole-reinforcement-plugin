"""OrcaSlicerのscaled座標2D幾何と純粋なmm値を相互変換する。"""

from collections.abc import Iterable

import orca

from .reinforcement import PlanarRegion, Polygon2, RegionSet


class OrcaPlanarGeometry:
    def __init__(self):
        self._scaled_per_mm = 1.0 / float(orca.slicing.unscale(1))

    def difference(self, subject: RegionSet, clips: RegionSet) -> RegionSet:
        current = self.to_host(subject)
        for clip in self.to_host(clips):
            current = [piece for region in current for piece in region.diff_ex(clip)]
        return self.from_host(current)

    def intersection(self, subject: RegionSet, clips: RegionSet) -> RegionSet:
        intersections = [
            piece
            for region in self.to_host(subject)
            for clip in self.to_host(clips)
            for piece in region.intersection_ex(clip)
        ]
        return self.from_host(self._union_host(intersections))

    def offset(self, regions: RegionSet, distance_mm: float) -> RegionSet:
        distance = int(round(distance_mm * self._scaled_per_mm))
        expanded = [
            piece for region in self.to_host(regions) for piece in region.offset(distance)
        ]
        return self.from_host(self._union_host(expanded))

    def union(self, regions: RegionSet) -> RegionSet:
        return self.from_host(self._union_host(self.to_host(regions)))

    def to_host(self, regions: RegionSet):
        return [
            orca.host.ExPolygon(
                self.polygon_to_host(region.contour_mm),
                [self.polygon_to_host(hole) for hole in region.holes_mm],
            )
            for region in regions
        ]

    def from_host(self, regions: Iterable[object]) -> RegionSet:
        return tuple(
            PlanarRegion(
                self.polygon_from_host(region.contour),
                tuple(self.polygon_from_host(hole) for hole in region.holes),
            )
            for region in regions
        )

    def polygon_to_host(self, polygon: Polygon2):
        result = orca.host.Polygon()
        for x_mm, y_mm in polygon:
            result.append(
                orca.host.Point(
                    int(round(x_mm * self._scaled_per_mm)),
                    int(round(y_mm * self._scaled_per_mm)),
                )
            )
        return result

    def polygon_from_host(self, polygon) -> Polygon2:
        return tuple(
            (
                float(point.x) / self._scaled_per_mm,
                float(point.y) / self._scaled_per_mm,
            )
            for point in polygon.points
        )

    @staticmethod
    def _union_host(regions):
        merged = list(regions)
        changed = True
        while changed:
            changed = False
            for first_index in range(len(merged)):
                for second_index in range(first_index + 1, len(merged)):
                    union = merged[first_index].union_ex(merged[second_index])
                    if len(union) == 1:
                        merged[first_index] = union[0]
                        del merged[second_index]
                        changed = True
                        break
                if changed:
                    break
        return merged
