import importlib
import sys
import types
import unittest

from orcaslicer_hole_reinforcement.reinforcement import PlanarRegion


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class Polygon:
    def __init__(self):
        self.points = []

    def append(self, point):
        self.points.append(point)


class ExPolygon:
    def __init__(self, contour, holes=None):
        self.contour = contour
        self.holes = list(holes or ())

    def union_ex(self, other):
        return [self]

    def diff_ex(self, other):
        return [self]

    def intersection_ex(self, other):
        return [self]

    def offset(self, distance):
        return [self]


class OrcaPlanarGeometryTests(unittest.TestCase):
    def setUp(self):
        orca = types.ModuleType("orca")
        orca.slicing = types.SimpleNamespace(unscale=lambda value: value / 1000.0)
        orca.host = types.SimpleNamespace(
            Point=Point,
            Polygon=Polygon,
            ExPolygon=ExPolygon,
        )
        sys.modules["orca"] = orca
        sys.modules.pop("orcaslicer_hole_reinforcement.orca_geometry", None)
        module = importlib.import_module(
            "orcaslicer_hole_reinforcement.orca_geometry"
        )
        self.geometry = module.OrcaPlanarGeometry()

    def tearDown(self):
        sys.modules.pop("orca", None)
        sys.modules.pop("orcaslicer_hole_reinforcement.orca_geometry", None)

    def test_round_trip_preserves_scaled_coordinates_and_hole_ownership(self):
        region = PlanarRegion(
            ((0.0, 0.0), (2.0, 0.0), (0.0, 2.0)),
            (((0.2, 0.2), (0.4, 0.2), (0.2, 0.4)),),
        )

        host = self.geometry.to_host((region,))
        restored = self.geometry.from_host(host)

        self.assertEqual(host[0].contour.points[1].x, 2000)
        self.assertEqual(host[0].holes[0].points[0].x, 200)
        self.assertEqual(restored, (region,))

    def test_boolean_operations_return_independent_value_copies(self):
        region = PlanarRegion(((0.0, 0.0), (2.0, 0.0), (0.0, 2.0)))

        self.assertEqual(self.geometry.difference((region,), (region,)), (region,))
        self.assertEqual(self.geometry.intersection((region,), (region,)), (region,))
        self.assertEqual(self.geometry.offset((region,), 2.0), (region,))
        self.assertEqual(self.geometry.union((region, region)), (region,))


if __name__ == "__main__":
    unittest.main()
