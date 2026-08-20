import tempfile
import unittest
from pathlib import Path

from tools.fixture_suite import ANGLES, DEFAULT_OUTPUT, SHAPES, cases, generate
from tools.fixture_suite import build_mesh, matrix_geometry
from tools.run_fixture_harness import _fixture_path, verify


def _section_extent(vertices, triangles, height):
    """指定した高さでの断面の広がり。プレートとの接触面積の代用にする。"""
    segments = []
    for first, second, third in triangles:
        corners = (vertices[first], vertices[second], vertices[third])
        crossings = []
        for start, end in ((corners[0], corners[1]), (corners[1], corners[2]), (corners[2], corners[0])):
            if (start[2] - height) * (end[2] - height) < 0:
                ratio = (height - start[2]) / (end[2] - start[2])
                crossings.append(
                    (start[0] + ratio * (end[0] - start[0]), start[1] + ratio * (end[1] - start[1]))
                )
        if len(crossings) == 2:
            segments.append(crossings)
    if not segments:
        return 0.0, 0.0
    xs = [x for segment in segments for x, _ in segment]
    ys = [y for segment in segments for _, y in segment]
    return max(xs) - min(xs), max(ys) - min(ys)


class FixtureSuiteTests(unittest.TestCase):
    def test_matrix_fixtures_leave_room_for_infill_around_the_hole(self):
        minimum_margin_mm = 8.0
        for case in cases():
            if not case.case_id.startswith("matrix-"):
                continue

            with self.subTest(case=case.case_id):
                vertices, _ = build_mesh(case)
                sides = SHAPES[case.shape]
                wall = vertices[: sides * 2]
                bounds = [
                    (
                        min(point[axis] for point in vertices),
                        max(point[axis] for point in vertices),
                    )
                    for axis in range(3)
                ]
                _, primary, _, _ = matrix_geometry(case)
                for axis in range(3):
                    if axis == primary:
                        # 穴が抜ける方向には材料を挟まない。
                        continue
                    self.assertGreaterEqual(
                        min(point[axis] for point in wall) - bounds[axis][0] + 1e-9,
                        minimum_margin_mm,
                    )
                    self.assertGreaterEqual(
                        bounds[axis][1] - max(point[axis] for point in wall) + 1e-9,
                        minimum_margin_mm,
                    )
                if case.end_kind == "blind":
                    floor = vertices[sides : sides * 2]
                    self.assertGreaterEqual(
                        min(point[primary] for point in floor) - bounds[primary][0] + 1e-9,
                        minimum_margin_mm,
                    )

    def test_matrix_fixtures_sit_flat_on_the_plate(self):
        """傾斜モデルがプレートへ線接触すると、OrcaSlicerが造形不可と判定する。"""
        minimum_contact_mm = 10.0
        for case in cases():
            if not case.case_id.startswith("matrix-"):
                continue

            with self.subTest(case=case.case_id):
                vertices, triangles = build_mesh(case)
                lowest = min(point[2] for point in vertices)
                width, depth = _section_extent(vertices, triangles, lowest + 0.2)
                self.assertGreaterEqual(min(width, depth), minimum_contact_mm)

    def test_matrix_fixture_outline_is_axis_aligned(self):
        """外形が傾いていると、どの向きでも接触面積を確保できない。"""
        for case in cases():
            if not case.case_id.startswith("matrix-"):
                continue

            with self.subTest(case=case.case_id):
                vertices, _ = build_mesh(case)
                bounds = [
                    (
                        min(point[axis] for point in vertices),
                        max(point[axis] for point in vertices),
                    )
                    for axis in range(3)
                ]
                corners = {
                    (x, y, z)
                    for x in bounds[0]
                    for y in bounds[1]
                    for z in bounds[2]
                }
                present = {point for point in vertices}
                self.assertTrue(corners <= present)

    def test_printable_fixtures_are_closed_two_manifold_meshes(self):
        for case in cases():
            if not case.printable:
                continue

            with self.subTest(case=case.case_id):
                _, triangles = build_mesh(case)
                edge_owners: dict[tuple[int, int], int] = {}
                for triangle in triangles:
                    for first, second in zip(triangle, triangle[1:] + triangle[:1]):
                        edge = tuple(sorted((first, second)))
                        edge_owners[edge] = edge_owners.get(edge, 0) + 1

                self.assertEqual(
                    [edge for edge, owners in edge_owners.items() if owners != 2],
                    [],
                )

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

    def test_intentionally_non_manifold_fixtures_are_marked_non_printable(self):
        non_printable = {case.case_id for case in cases() if not case.printable}

        self.assertEqual(
            non_printable,
            {"negative-open-groove", "negative-broken-mesh"},
        )


if __name__ == "__main__":
    unittest.main()
