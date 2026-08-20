import math
import unittest

from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.detection import (
    CylindricalHoleCandidate,
    HoleEndKind,
)
from orcaslicer_hole_reinforcement.end_classification import (
    ClassifiedHole,
    HoleEndState,
)
from orcaslicer_hole_reinforcement.polygon_detection import PolygonalHoleDetector
from orcaslicer_hole_reinforcement.reinforcement import (
    LayerHoleContour,
    LayerPlane,
    ReinforcementPlanningCancelled,
    ReinforcementVolumeSlicer,
)
from tests.test_polygon_detection import polygon_side


MODEL = (((-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)),)


def apothem(polygon):
    distances = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        numerator = abs(first[0] * second[1] - first[1] * second[0])
        denominator = math.dist(first, second)
        distances.append(numerator / denominator)
    return min(distances)


class RecordingGeometry:
    def __init__(self):
        self.differences = []
        self.intersections = []
        self.offsets = []
        self.unions = []

    def difference(self, subject, clips):
        self.differences.append((subject, clips))
        return subject

    def intersection(self, subject, clips):
        self.intersections.append((subject, clips))
        return subject if clips else ()

    def offset(self, polygons, distance_mm):
        self.offsets.append((polygons, distance_mm))
        return polygons

    def union(self, polygons):
        self.unions.append(polygons)
        return polygons


def classified_circle(axis=(0.0, 0.0, 1.0), accepted=True):
    length = sum(value * value for value in axis) ** 0.5
    axis = tuple(value / length for value in axis)
    candidate = CylindricalHoleCandidate(
        center_mm=(0.0, 0.0, 0.0),
        axis=axis,
        radius_mm=2.0,
        depth_mm=8.0,
        axial_start_mm=-4.0,
        axial_end_mm=4.0,
        confidence=1.0,
        triangle_indices=(),
    )
    return ClassifiedHole(
        candidate,
        HoleEndState.OPEN,
        HoleEndState.OPEN,
        HoleEndKind.THROUGH,
        accepted,
        "both_ends_open",
    )


def classified_polygon(sides):
    candidate = PolygonalHoleDetector().detect(
        polygon_side(sides), HoleReinforcementConfig()
    )[0]
    return ClassifiedHole(
        candidate,
        HoleEndState.OPEN,
        HoleEndState.OPEN,
        HoleEndKind.THROUGH,
        True,
        "both_ends_open",
    )


class ReinforcementVolumeSlicerTests(unittest.TestCase):
    def setUp(self):
        self.geometry = RecordingGeometry()
        self.slicer = ReinforcementVolumeSlicer(self.geometry)
        self.config = HoleReinforcementConfig(reinforcement_width_mm=2.0)

    def test_slices_vertical_circle_with_three_dimensional_width(self):
        result = self.slicer.plan(
            (classified_circle(),), (LayerPlane(0, 0.0, MODEL),), self.config
        )

        self.assertEqual(len(result), 1)
        outer = self.geometry.differences[0][0][0]
        inner = self.geometry.differences[0][1][0]
        self.assertAlmostEqual(apothem(outer), 4.0, places=6)
        self.assertAlmostEqual(apothem(inner), 2.0, places=6)
        self.assertGreaterEqual(len(outer), 32)

    def test_generates_continuous_layers_for_all_axis_directions(self):
        layers = tuple(LayerPlane(index, z, MODEL) for index, z in enumerate((-1.0, 0.0, 1.0)))
        for axis in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (1.0, 1.0, 1.0)):
            with self.subTest(axis=axis):
                geometry = RecordingGeometry()
                result = ReinforcementVolumeSlicer(geometry).plan(
                    (classified_circle(axis),), layers, self.config
                )
                self.assertEqual(tuple(region.layer_index for region in result), (0, 1, 2))

    def test_supports_hexagon_octagon_and_regular_polygon(self):
        for sides in (6, 8, 12):
            with self.subTest(sides=sides):
                geometry = RecordingGeometry()
                result = ReinforcementVolumeSlicer(geometry).plan(
                    (classified_polygon(sides),),
                    (LayerPlane(0, 0.0, MODEL),),
                    self.config,
                )
                self.assertEqual(len(result), 1)
                outer = geometry.differences[0][0][0]
                inner = geometry.differences[0][1][0]
                self.assertAlmostEqual(apothem(outer) - apothem(inner), 2.0, places=6)

    def test_uses_post_slice_hole_contour_for_polyhole_compatibility(self):
        actual_contour = ((-1.5, -2.0), (1.5, -2.0), (2.0, 0.0), (0.0, 2.2), (-2.0, 0.0))
        layer = LayerPlane(
            0,
            0.0,
            MODEL,
            (LayerHoleContour(0, actual_contour),),
        )

        self.slicer.plan((classified_circle(),), (layer,), self.config)

        self.assertEqual(self.geometry.differences[0][1], (actual_contour,))
        self.assertEqual(self.geometry.offsets, [((actual_contour,), 2.0)])

    def test_clips_each_layer_to_model_contours(self):
        self.slicer.plan(
            (classified_circle(),), (LayerPlane(7, 0.0, MODEL),), self.config
        )

        self.assertEqual(len(self.geometry.intersections), 1)
        self.assertEqual(self.geometry.intersections[0][1], MODEL)

    def test_omits_tangent_layer_that_has_no_polygon_area(self):
        result = self.slicer.plan(
            (classified_circle(axis=(1.0, 0.0, 0.0)),),
            (LayerPlane(0, 4.0, MODEL),),
            self.config,
        )

        self.assertEqual(result, ())
        self.assertEqual(self.geometry.differences, [])

    def test_keeps_layer_where_only_outer_volume_intersects(self):
        result = self.slicer.plan(
            (classified_circle(axis=(1.0, 0.0, 0.0)),),
            (LayerPlane(0, 3.0, MODEL),),
            self.config,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(self.geometry.differences[0][1], ())

    def test_ignores_rejected_holes_and_disabled_reinforcement(self):
        layer = LayerPlane(0, 0.0, MODEL)
        self.assertEqual(
            self.slicer.plan((classified_circle(accepted=False),), (layer,), self.config),
            (),
        )
        self.assertEqual(
            self.slicer.plan(
                (classified_circle(),),
                (layer,),
                HoleReinforcementConfig(solid_reinforcement=False),
            ),
            (),
        )

    def test_honours_cancellation(self):
        with self.assertRaises(ReinforcementPlanningCancelled):
            self.slicer.plan(
                (classified_circle(),),
                (LayerPlane(0, 0.0, MODEL),),
                self.config,
                cancelled=lambda: True,
            )


if __name__ == "__main__":
    unittest.main()
