import tempfile
import unittest
from pathlib import Path

from tools.fixture_suite import ANGLES, DEFAULT_OUTPUT, SHAPES, cases, generate
from tools.run_fixture_harness import _fixture_path, verify


class FixtureSuiteTests(unittest.TestCase):
    def test_covers_shape_end_and_direction_matrix(self):
        matrix = {
            (case.shape, case.end_kind, case.angle_deg)
            for case in cases()
            if case.case_id.startswith("matrix-")
        }

        self.assertEqual(
            matrix,
            {
                (shape, end_kind, angle)
                for shape in SHAPES
                for end_kind in ("through", "blind")
                for angle in ANGLES
            },
        )

    def test_generation_matches_committed_fixtures_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            generate(generated)
            expected_files = sorted(path.name for path in DEFAULT_OUTPUT.iterdir())
            actual_files = sorted(path.name for path in generated.iterdir())

            self.assertEqual(actual_files, expected_files)
            for name in expected_files:
                with self.subTest(name=name):
                    self.assertEqual(
                        (generated / name).read_bytes(),
                        (DEFAULT_OUTPUT / name).read_bytes(),
                    )

    def test_all_committed_fixtures_match_expected_detection(self):
        self.assertEqual(verify(DEFAULT_OUTPUT), [])

    def test_manifest_file_cannot_escape_fixture_directory(self):
        with self.assertRaises(ValueError):
            _fixture_path(DEFAULT_OUTPUT, "../outside.stl")


if __name__ == "__main__":
    unittest.main()
