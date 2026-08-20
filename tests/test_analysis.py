import unittest
from unittest.mock import patch

from orcaslicer_hole_reinforcement.analysis import AnalysisCancelled, HoleAnalysisCache
from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.detection import CylindricalHoleCandidate, MeshSnapshot
from orcaslicer_hole_reinforcement.diagnostics import (
    MemoryDiagnosticSink,
    NullDiagnosticSink,
)
from orcaslicer_hole_reinforcement.end_classification import (
    ClassifiedHole,
    HoleEndState,
)


def mesh(offset=0.0):
    return MeshSnapshot(
        vertices_mm=(
            (offset, 0.0, 0.0),
            (offset + 1.0, 0.0, 0.0),
            (offset, 1.0, 0.0),
        ),
        triangles=((0, 1, 2),),
    )


def classified(center=(0.5, 0.5, 0.0)):
    candidate = CylindricalHoleCandidate(
        center_mm=center,
        axis=(1.0, 0.0, 0.0),
        radius_mm=0.25,
        depth_mm=1.0,
        axial_start_mm=0.0,
        axial_end_mm=1.0,
        confidence=1.0,
        triangle_indices=(0,),
    )
    return (
        ClassifiedHole(
            candidate,
            HoleEndState.OPEN,
            HoleEndState.OPEN,
            None,
            False,
            "test",
        ),
    )


class HoleAnalysisCacheTests(unittest.TestCase):
    def test_reuses_translated_shape_and_rebases_geometric_results(self):
        cache = HoleAnalysisCache()
        detector = unittest.mock.Mock()
        detector.detect.return_value = (object(),)
        classifier = unittest.mock.Mock()
        classifier.classify.return_value = classified()

        with (
            patch("orcaslicer_hole_reinforcement.analysis.HoleCandidateDetector", return_value=detector),
            patch("orcaslicer_hole_reinforcement.analysis.HoleEndClassifier", return_value=classifier),
        ):
            first, first_measurement = cache.analyze(
                mesh(), HoleReinforcementConfig(), diagnostics=NullDiagnosticSink()
            )
            second, second_measurement = cache.analyze(
                mesh(10.0), HoleReinforcementConfig(), diagnostics=NullDiagnosticSink()
            )

        self.assertFalse(first_measurement.cache_hit)
        self.assertTrue(second_measurement.cache_hit)
        self.assertEqual(detector.detect.call_count, 1)
        self.assertEqual(first[0].candidate.center_mm, (0.5, 0.5, 0.0))
        self.assertEqual(second[0].candidate.center_mm, (10.5, 0.5, 0.0))
        self.assertEqual(second[0].candidate.axial_start_mm, 10.0)

    def test_invalidates_for_shape_and_config_changes(self):
        cache = HoleAnalysisCache()
        detector = unittest.mock.Mock()
        detector.detect.return_value = (object(),)
        classifier = unittest.mock.Mock()
        classifier.classify.return_value = classified()
        changed_mesh = MeshSnapshot(
            vertices_mm=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            triangles=((0, 1, 2),),
        )

        with (
            patch("orcaslicer_hole_reinforcement.analysis.HoleCandidateDetector", return_value=detector),
            patch("orcaslicer_hole_reinforcement.analysis.HoleEndClassifier", return_value=classifier),
        ):
            cache.analyze(mesh(), HoleReinforcementConfig(), diagnostics=NullDiagnosticSink())
            cache.analyze(changed_mesh, HoleReinforcementConfig(), diagnostics=NullDiagnosticSink())
            cache.analyze(
                mesh(),
                HoleReinforcementConfig(max_hole_diameter_mm=9.0),
                diagnostics=NullDiagnosticSink(),
            )

        self.assertEqual(detector.detect.call_count, 3)

    def test_reemits_classification_diagnostics_on_cache_hit(self):
        cache = HoleAnalysisCache()
        detector = unittest.mock.Mock()
        detector.detect.return_value = (object(),)
        classifier = unittest.mock.Mock()
        classifier.classify.return_value = classified()
        diagnostics = MemoryDiagnosticSink()

        with (
            patch("orcaslicer_hole_reinforcement.analysis.HoleCandidateDetector", return_value=detector),
            patch("orcaslicer_hole_reinforcement.analysis.HoleEndClassifier", return_value=classifier),
        ):
            cache.analyze(mesh(), HoleReinforcementConfig(), diagnostics=diagnostics)
            cache.analyze(mesh(10.0), HoleReinforcementConfig(), diagnostics=diagnostics)

        self.assertEqual(len(diagnostics.events), 1)
        self.assertEqual(diagnostics.events[0].details["center_mm"], (10.5, 0.5, 0.0))

    def test_honours_cancellation_while_fingerprinting(self):
        cache = HoleAnalysisCache()
        large = MeshSnapshot(
            vertices_mm=((0.0, 0.0, 0.0),) * 4097,
            triangles=((0, 0, 0),),
        )
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks == 2

        with self.assertRaises(AnalysisCancelled):
            cache.analyze(
                large,
                HoleReinforcementConfig(),
                diagnostics=NullDiagnosticSink(),
                cancelled=cancelled,
            )


if __name__ == "__main__":
    unittest.main()
