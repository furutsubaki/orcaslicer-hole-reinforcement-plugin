import unittest

from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.detection import HoleEndKind, MeshSnapshot
from orcaslicer_hole_reinforcement.end_classification import (
    HoleEndClassificationCancelled,
    HoleEndClassifier,
    HoleEndState,
)
from orcaslicer_hole_reinforcement.polygon_detection import PolygonalHoleDetector
from tests.test_polygon_detection import polygon_side


class RecordingDiagnostics:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def hole_with_ends(start, end, sides=8, **wall_options):
    wall = polygon_side(sides, **wall_options)
    vertices = list(wall.vertices_mm)
    triangles = list(wall.triangles)
    for level, kind in ((0, start), (1, end)):
        rim = tuple(level * sides + index for index in range(sides))
        if kind == "open_slanted":
            for index in rim:
                x, y, z = vertices[index]
                vertices[index] = (x, y, z + x * 0.2)
        endpoint_center = tuple(
            sum(vertices[index][coordinate] for index in rim) / sides
            for coordinate in range(3)
        )
        if kind in ("open", "open_slanted"):
            outer = []
            for index in rim:
                outer.append(len(vertices))
                vertices.append(
                    tuple(
                        endpoint_center[coordinate]
                        + (vertices[index][coordinate] - endpoint_center[coordinate])
                        * 1.8
                        for coordinate in range(3)
                    )
                )
            for index in range(sides):
                following = (index + 1) % sides
                triangles.extend(
                    (
                        (rim[index], outer[index], outer[following]),
                        (rim[index], outer[following], rim[following]),
                    )
                )
        elif kind == "closed":
            center = len(vertices)
            vertices.append(endpoint_center)
            for index in range(sides):
                triangles.append((rim[index], center, rim[(index + 1) % sides]))
        elif kind == "closed_subdivided":
            inner = []
            for index in rim:
                inner.append(len(vertices))
                vertices.append(
                    tuple(
                        endpoint_center[coordinate]
                        + (vertices[index][coordinate] - endpoint_center[coordinate])
                        * 0.4
                        for coordinate in range(3)
                    )
                )
            for index in range(sides):
                following = (index + 1) % sides
                triangles.extend(
                    (
                        (rim[index], inner[index], inner[following]),
                        (rim[index], inner[following], rim[following]),
                    )
                )
            center = len(vertices)
            vertices.append(endpoint_center)
            for index in range(sides):
                triangles.append((inner[index], center, inner[(index + 1) % sides]))
    return wall, MeshSnapshot(tuple(vertices), tuple(triangles))


class HoleEndClassifierTests(unittest.TestCase):
    def setUp(self):
        self.classifier = HoleEndClassifier()
        self.config = HoleReinforcementConfig()

    def classify(self, start, end, config=None, diagnostics=None):
        wall, mesh = hole_with_ends(start, end)
        candidate = PolygonalHoleDetector().detect(wall, self.config)[0]
        return self.classifier.classify(
            mesh,
            (candidate,),
            config or self.config,
            diagnostics=diagnostics or RecordingDiagnostics(),
        )[0]

    def test_classifies_two_open_ends_as_through_hole(self):
        result = self.classify("open", "open")

        self.assertIs(result.start_state, HoleEndState.OPEN)
        self.assertIs(result.end_state, HoleEndState.OPEN)
        self.assertIs(result.end_kind, HoleEndKind.THROUGH)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "both_ends_open")

    def test_classifies_opening_on_slanted_outer_surface(self):
        wall, mesh = hole_with_ends("open", "open_slanted")
        candidate = PolygonalHoleDetector().detect(wall, self.config)[0]

        result = self.classifier.classify(mesh, (candidate,), self.config)[0]

        self.assertIs(result.end_kind, HoleEndKind.THROUGH)
        self.assertTrue(result.accepted)

    def test_classifies_one_closed_end_as_blind_hole(self):
        result = self.classify("open", "closed")

        self.assertIs(result.start_state, HoleEndState.OPEN)
        self.assertIs(result.end_state, HoleEndState.CLOSED)
        self.assertIs(result.end_kind, HoleEndKind.BLIND)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "one_end_closed")

    def test_classification_is_independent_of_axis_and_position(self):
        wall, mesh = hole_with_ends(
            "open",
            "closed",
            axis=(1.0, 2.0, 3.0),
            center=(4.0, 5.0, 6.0),
        )
        candidate = PolygonalHoleDetector().detect(wall, self.config)[0]

        result = self.classifier.classify(mesh, (candidate,), self.config)[0]

        self.assertIs(result.end_kind, HoleEndKind.BLIND)
        self.assertTrue(result.accepted)

    def test_follows_subdivided_end_surface_to_find_closed_center(self):
        result = self.classify("open", "closed_subdivided")

        self.assertIs(result.end_kind, HoleEndKind.BLIND)
        self.assertTrue(result.accepted)

    def test_excludes_broken_rim_as_uncertain(self):
        result = self.classify("open", "broken")

        self.assertIs(result.end_state, HoleEndState.UNCERTAIN)
        self.assertIsNone(result.end_kind)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "incomplete_or_non_manifold_rim")

    def test_excludes_internal_cavity_with_two_closed_ends(self):
        result = self.classify("closed", "closed")

        self.assertIsNone(result.end_kind)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "both_ends_closed")

    def test_applies_enabled_end_kinds(self):
        result = self.classify(
            "open",
            "closed",
            HoleReinforcementConfig(enabled_end_kinds=("through",)),
        )

        self.assertIs(result.end_kind, HoleEndKind.BLIND)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "blind_disabled")

    def test_emits_classification_reason(self):
        diagnostics = RecordingDiagnostics()
        result = self.classify("open", "open", diagnostics=diagnostics)

        self.assertTrue(result.accepted)
        self.assertEqual(len(diagnostics.events), 1)
        self.assertEqual(diagnostics.events[0].code, "hole_end_classified")
        self.assertEqual(diagnostics.events[0].details["reason"], "both_ends_open")
        self.assertEqual(diagnostics.events[0].details["shape"], "octagon")
        self.assertAlmostEqual(diagnostics.events[0].details["diameter_mm"], 4.0)
        self.assertEqual(diagnostics.events[0].details["side_count"], 8)
        self.assertEqual(diagnostics.events[0].details["axis"], result.candidate.axis)

    def test_honours_cancellation(self):
        wall, mesh = hole_with_ends("open", "open")
        candidate = PolygonalHoleDetector().detect(wall, self.config)[0]

        with self.assertRaises(HoleEndClassificationCancelled):
            self.classifier.classify(
                mesh, (candidate,), self.config, cancelled=lambda: True
            )


if __name__ == "__main__":
    unittest.main()
