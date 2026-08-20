import math
import unittest

from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.cylinder_detection import (
    CylinderDetectionCancelled,
    CylindricalHoleDetector,
)
from orcaslicer_hole_reinforcement.detection import MeshSnapshot


def cylinder_side(
    *,
    axis=(0.0, 0.0, 1.0),
    center=(0.0, 0.0, 0.0),
    radius=2.0,
    radius_v=None,
    depth=8.0,
    segments=24,
    inward=True,
    covered_segments=None,
):
    radius_v = radius if radius_v is None else radius_v
    axis = normalize(axis)
    reference = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    basis_u = normalize(cross(axis, reference))
    basis_v = cross(axis, basis_u)
    ring_count = segments if covered_segments is None else covered_segments + 1
    vertices = []
    for axial in (-depth / 2.0, depth / 2.0):
        for index in range(ring_count):
            angle = 2.0 * math.pi * index / segments
            vertices.append(
                tuple(
                    center[coordinate]
                    + axis[coordinate] * axial
                    + radius
                    * basis_u[coordinate]
                    * math.cos(angle)
                    + radius_v * basis_v[coordinate] * math.sin(angle)
                    for coordinate in range(3)
                )
            )
    triangles = []
    face_count = segments if covered_segments is None else covered_segments
    for index in range(face_count):
        next_index = (index + 1) % ring_count
        bottom_first = index
        bottom_second = next_index
        top_first = ring_count + index
        top_second = ring_count + next_index
        if inward:
            triangles.extend(
                ((bottom_first, top_second, bottom_second), (bottom_first, top_first, top_second))
            )
        else:
            triangles.extend(
                ((bottom_first, bottom_second, top_second), (bottom_first, top_second, top_first))
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


class CylindricalHoleDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = CylindricalHoleDetector()
        self.config = HoleReinforcementConfig(
            min_hole_diameter_mm=1.0,
            max_hole_diameter_mm=10.0,
            min_hole_depth_mm=2.0,
            circle_radial_tolerance_mm=0.05,
        )

    def test_detects_vertical_horizontal_and_inclined_holes(self):
        for axis in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (1.0, 1.0, 1.0)):
            with self.subTest(axis=axis):
                result = self.detector.detect(cylinder_side(axis=axis), self.config)
                self.assertEqual(len(result), 1)
                candidate = result[0]
                self.assertAlmostEqual(abs(sum(a * b for a, b in zip(candidate.axis, normalize(axis)))), 1.0)
                self.assertAlmostEqual(candidate.radius_mm, 2.0, places=6)
                self.assertAlmostEqual(candidate.depth_mm, 8.0, places=6)

    def test_recovers_translated_center(self):
        result = self.detector.detect(
            cylinder_side(axis=(1.0, 1.0, 0.0), center=(3.0, 4.0, 5.0)),
            self.config,
        )
        self.assertEqual(len(result), 1)
        for actual, expected in zip(result[0].center_mm, (3.0, 4.0, 5.0)):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_is_stable_across_mesh_segment_counts(self):
        results = [
            self.detector.detect(cylinder_side(segments=segments), self.config)[0]
            for segments in (12, 24, 48)
        ]
        self.assertTrue(all(abs(item.radius_mm - 2.0) < 1e-6 for item in results))
        self.assertTrue(all(abs(item.depth_mm - 8.0) < 1e-6 for item in results))

    def test_excludes_diameter_above_limit(self):
        config = HoleReinforcementConfig(max_hole_diameter_mm=3.9)
        self.assertEqual(self.detector.detect(cylinder_side(radius=2.0), config), ())

    def test_excludes_outer_cylinder_surface(self):
        self.assertEqual(self.detector.detect(cylinder_side(inward=False), self.config), ())

    def test_excludes_open_arc_groove(self):
        mesh = cylinder_side(segments=24, covered_segments=18)
        self.assertEqual(self.detector.detect(mesh, self.config), ())

    def test_excludes_cross_section_outside_radial_tolerance(self):
        mesh = cylinder_side(radius=2.0, radius_v=2.2)
        self.assertEqual(self.detector.detect(mesh, self.config), ())

    def test_respects_shape_configuration(self):
        config = HoleReinforcementConfig(enabled_shapes=("hexagon",))
        self.assertEqual(self.detector.detect(cylinder_side(), config), ())

    def test_honours_cancellation_during_triangle_scan(self):
        with self.assertRaises(CylinderDetectionCancelled):
            self.detector.detect(cylinder_side(), self.config, cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main()
