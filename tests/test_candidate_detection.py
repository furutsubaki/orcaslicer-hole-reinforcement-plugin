import unittest

from orcaslicer_hole_reinforcement.candidate_detection import HoleCandidateDetector
from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.detection import PolygonalHoleCandidate
from tests.test_cylinder_detection import cylinder_side
from tests.test_polygon_detection import polygon_side


class HoleCandidateDetectorTests(unittest.TestCase):
    def test_prefers_polygon_when_detectors_match_same_mesh_faces(self):
        result = HoleCandidateDetector().detect(
            polygon_side(12), HoleReinforcementConfig()
        )

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], PolygonalHoleCandidate)
        self.assertEqual(result[0].side_count, 12)

    def test_keeps_circle_when_regular_polygon_is_disabled(self):
        result = HoleCandidateDetector().detect(
            polygon_side(12),
            HoleReinforcementConfig(enabled_shapes=("circle",)),
        )

        self.assertEqual(len(result), 1)

    def test_keeps_high_resolution_cylinder_outside_polygon_side_range(self):
        result = HoleCandidateDetector().detect(
            cylinder_side(segments=96), HoleReinforcementConfig()
        )

        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
