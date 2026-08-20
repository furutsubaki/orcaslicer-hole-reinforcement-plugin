import math
import unittest

from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.detection import HoleShape, MeshSnapshot
from orcaslicer_hole_reinforcement.polygon_detection import (
    PolygonDetectionCancelled,
    PolygonalHoleDetector,
)


def polygon_side(
    side_count,
    *,
    axis=(0.0, 0.0, 1.0),
    center=(0.0, 0.0, 0.0),
    across_flats=4.0,
    depth=8.0,
    phase=0.0,
    levels=1,
    inward=True,
    radial_scales=None,
    alternate_diagonal=False,
):
    axis = normalize(axis)
    reference = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    basis_u = normalize(cross(axis, reference))
    basis_v = cross(axis, basis_u)
    circumradius = across_flats / (2.0 * math.cos(math.pi / side_count))
    radial_scales = radial_scales or (1.0,) * side_count
    vertices = []
    for level in range(levels + 1):
        axial = -depth / 2.0 + depth * level / levels
        for index in range(side_count):
            angle = phase + 2.0 * math.pi * index / side_count
            radius = circumradius * radial_scales[index]
            vertices.append(
                tuple(
                    center[coordinate]
                    + axis[coordinate] * axial
                    + radius * basis_u[coordinate] * math.cos(angle)
                    + radius * basis_v[coordinate] * math.sin(angle)
                    for coordinate in range(3)
                )
            )
    triangles = []
    for level in range(levels):
        for index in range(side_count):
            following = (index + 1) % side_count
            bottom_first = level * side_count + index
            bottom_second = level * side_count + following
            top_first = (level + 1) * side_count + index
            top_second = (level + 1) * side_count + following
            flip = alternate_diagonal and (level + index) % 2
            if flip:
                outward = (
                    (bottom_first, bottom_second, top_first),
                    (bottom_second, top_second, top_first),
                )
            else:
                outward = (
                    (bottom_first, bottom_second, top_second),
                    (bottom_first, top_second, top_first),
                )
            triangles.extend(
                tuple(reversed(triangle)) if inward else triangle for triangle in outward
            )
    return MeshSnapshot(tuple(vertices), tuple(triangles))


def normalize(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return tuple(value / length for value in vector)


def cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


class PolygonalHoleDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = PolygonalHoleDetector()
        self.config = HoleReinforcementConfig(
            min_hole_diameter_mm=1.0,
            max_hole_diameter_mm=10.0,
            min_hole_depth_mm=2.0,
            polygon_edge_length_tolerance_percent=2.0,
            polygon_angle_tolerance_deg=1.0,
        )

    def test_detects_hexagon_and_octagon(self):
        for sides, shape in ((6, HoleShape.HEXAGON), (8, HoleShape.OCTAGON)):
            with self.subTest(sides=sides):
                result = self.detector.detect(polygon_side(sides), self.config)
                self.assertEqual(len(result), 1)
                self.assertIs(result[0].shape, shape)
                self.assertEqual(len(result[0].cross_section_mm), sides)
                self.assertAlmostEqual(result[0].across_flats_mm, 4.0, places=6)
                self.assertAlmostEqual(result[0].depth_mm, 8.0, places=6)

    def test_detects_regular_polygon_with_arbitrary_side_count(self):
        result = self.detector.detect(polygon_side(12), self.config)

        self.assertEqual(len(result), 1)
        self.assertIs(result[0].shape, HoleShape.REGULAR_POLYGON)
        self.assertEqual(result[0].side_count, 12)
        self.assertEqual(len(result[0].cross_section_mm), 12)

    def test_is_independent_of_axis_and_rotation_phase(self):
        mesh = polygon_side(
            6,
            axis=(1.0, 2.0, 3.0),
            center=(4.0, 5.0, 6.0),
            phase=0.37,
        )
        result = self.detector.detect(mesh, self.config)
        self.assertEqual(len(result), 1)
        for actual, expected in zip(result[0].center_mm, (4.0, 5.0, 6.0)):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_respects_individual_shape_configuration(self):
        hexagon_only = HoleReinforcementConfig(enabled_shapes=("hexagon",))
        octagon_only = HoleReinforcementConfig(enabled_shapes=("octagon",))
        self.assertEqual(len(self.detector.detect(polygon_side(6), hexagon_only)), 1)
        self.assertEqual(self.detector.detect(polygon_side(8), hexagon_only), ())
        self.assertEqual(len(self.detector.detect(polygon_side(8), octagon_only)), 1)
        self.assertEqual(self.detector.detect(polygon_side(6), octagon_only), ())

    def test_respects_regular_polygon_side_range(self):
        config = HoleReinforcementConfig(
            enabled_shapes=("regular_polygon",),
            min_polygon_sides=10,
            max_polygon_sides=16,
        )

        self.assertEqual(self.detector.detect(polygon_side(8), config), ())
        self.assertEqual(len(self.detector.detect(polygon_side(12), config)), 1)
        self.assertEqual(self.detector.detect(polygon_side(20), config), ())

    def test_excludes_irregular_polygon(self):
        mesh = polygon_side(6, radial_scales=(1.15, 1.0, 1.0, 1.0, 1.0, 1.0))
        self.assertEqual(self.detector.detect(mesh, self.config), ())

    def test_excludes_outer_polygon_surface(self):
        self.assertEqual(
            self.detector.detect(polygon_side(8, inward=False), self.config), ()
        )

    def test_excludes_degenerate_cross_section_without_error(self):
        mesh = polygon_side(6, radial_scales=(0.0, 1.0, 1.0, 1.0, 1.0, 1.0))
        self.assertEqual(self.detector.detect(mesh, self.config), ())

    def test_is_stable_across_triangulation(self):
        first = self.detector.detect(polygon_side(8), self.config)[0]
        second = self.detector.detect(
            polygon_side(8, levels=3, alternate_diagonal=True), self.config
        )[0]
        self.assertAlmostEqual(first.across_flats_mm, second.across_flats_mm, places=6)
        self.assertAlmostEqual(first.depth_mm, second.depth_mm, places=6)

    def test_honours_cancellation_during_triangle_scan(self):
        with self.assertRaises(PolygonDetectionCancelled):
            self.detector.detect(polygon_side(6), self.config, cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main()
