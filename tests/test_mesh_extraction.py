import unittest

from orcaslicer_hole_reinforcement.mesh_extraction import (
    MeshExtractionCancelled,
    MeshExtractionError,
    VolumeRole,
    extract_transformed_volumes,
)


IDENTITY = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


class FakeMesh:
    def __init__(self, vertices=((1.0, 2.0, 3.0),), triangles=((0, 0, 0),)):
        self._vertices = vertices
        self._triangles = triangles

    def vertices(self):
        return self._vertices

    def triangles(self):
        return self._triangles


class FakeVolume:
    def __init__(self, volume_id, role, matrix=IDENTITY, mesh=None):
        self._id = volume_id
        self._role = role
        self._matrix = matrix
        self._mesh = mesh or FakeMesh()

    def id(self):
        return self._id

    def is_model_part(self):
        return self._role == "model"

    def is_negative_volume(self):
        return self._role == "negative"

    def matrix(self):
        return self._matrix

    def mesh(self):
        return self._mesh


class FakeModelObject:
    def __init__(self, object_id, volumes):
        self._id = object_id
        self._volumes = volumes

    def id(self):
        return self._id

    def volume_count(self):
        return len(self._volumes)

    def volume(self, index):
        return self._volumes[index]


class FakePrintObject:
    def __init__(self, print_id, model_object, matrix=IDENTITY):
        self._id = print_id
        self._model_object = model_object
        self._matrix = matrix

    def id(self):
        return self._id

    def model_object(self):
        return self._model_object

    def trafo(self):
        return self._matrix


class MeshExtractionTests(unittest.TestCase):
    def test_applies_volume_then_print_transform_with_non_uniform_scale_and_rotation(self):
        volume_matrix = (
            (2.0, 0.0, 0.0, 5.0),
            (0.0, 3.0, 0.0, 7.0),
            (0.0, 0.0, 4.0, 11.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        print_matrix = (
            (0.0, -1.0, 0.0, 100.0),
            (1.0, 0.0, 0.0, 200.0),
            (0.0, 0.0, 1.0, 300.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        source = FakePrintObject(
            101,
            FakeModelObject(201, [FakeVolume(301, "model", volume_matrix)]),
            print_matrix,
        )

        snapshot = extract_transformed_volumes(source)[0]

        self.assertEqual(snapshot.mesh.vertices_mm, ((87.0, 207.0, 323.0),))
        self.assertEqual(snapshot.print_object_id, 101)
        self.assertEqual(snapshot.model_object_id, 201)
        self.assertEqual(snapshot.volume_id, 301)

    def test_keeps_model_and_negative_volumes_but_skips_modifiers(self):
        source = FakePrintObject(
            1,
            FakeModelObject(
                2,
                [
                    FakeVolume(10, "model"),
                    FakeVolume(11, "negative"),
                    FakeVolume(12, "modifier"),
                ],
            ),
        )

        snapshots = extract_transformed_volumes(source)

        self.assertEqual(
            tuple(snapshot.role for snapshot in snapshots),
            (VolumeRole.MODEL_PART, VolumeRole.NEGATIVE),
        )
        self.assertEqual(tuple(snapshot.volume_index for snapshot in snapshots), (0, 1))

    def test_mirror_reverses_triangle_winding(self):
        mirror = (
            (-1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        mesh = FakeMesh(
            vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            triangles=((0, 1, 2),),
        )
        source = FakePrintObject(
            1, FakeModelObject(2, [FakeVolume(3, "model", mirror, mesh)])
        )

        snapshot = extract_transformed_volumes(source)[0]

        self.assertEqual(snapshot.mesh.vertices_mm[1], (-1.0, 0.0, 0.0))
        self.assertEqual(snapshot.mesh.triangles, ((0, 2, 1),))

    def test_distinguishes_two_print_instances_of_same_model_object(self):
        model_object = FakeModelObject(20, [FakeVolume(30, "model")])
        first = extract_transformed_volumes(FakePrintObject(10, model_object))[0]
        second_matrix = tuple(
            tuple(value + (50.0 if row == 0 and column == 3 else 0.0) for column, value in enumerate(values))
            for row, values in enumerate(IDENTITY)
        )
        second = extract_transformed_volumes(
            FakePrintObject(11, model_object, second_matrix)
        )[0]

        self.assertNotEqual(first.print_object_id, second.print_object_id)
        self.assertEqual(first.model_object_id, second.model_object_id)
        self.assertEqual(first.mesh.vertices_mm, ((1.0, 2.0, 3.0),))
        self.assertEqual(second.mesh.vertices_mm, ((51.0, 2.0, 3.0),))

    def test_copies_host_views_before_returning(self):
        vertices = [[1.0, 2.0, 3.0]]
        triangles = [[0, 0, 0]]
        source = FakePrintObject(
            1,
            FakeModelObject(
                2, [FakeVolume(3, "model", mesh=FakeMesh(vertices, triangles))]
            ),
        )

        snapshot = extract_transformed_volumes(source)[0]
        vertices[0][0] = 99.0
        triangles[0][1] = 99

        self.assertEqual(snapshot.mesh.vertices_mm, ((1.0, 2.0, 3.0),))
        self.assertEqual(snapshot.mesh.triangles, ((0, 0, 0),))

    def test_rejects_invalid_triangle_index(self):
        source = FakePrintObject(
            1,
            FakeModelObject(
                2,
                [FakeVolume(3, "model", mesh=FakeMesh(triangles=((0, 1, 2),)))],
            ),
        )

        with self.assertRaises(MeshExtractionError):
            extract_transformed_volumes(source)

    def test_honours_cancellation_between_volumes(self):
        source = FakePrintObject(
            1, FakeModelObject(2, [FakeVolume(3, "model"), FakeVolume(4, "model")])
        )

        with self.assertRaises(MeshExtractionCancelled):
            extract_transformed_volumes(source, cancelled=lambda: True)

    def test_honours_cancellation_during_large_mesh_copy(self):
        vertices = ((1.0, 2.0, 3.0),) * 4097
        source = FakePrintObject(
            1,
            FakeModelObject(
                2, [FakeVolume(3, "model", mesh=FakeMesh(vertices, ((0, 0, 0),)))]
            ),
        )
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks == 3

        with self.assertRaises(MeshExtractionCancelled):
            extract_transformed_volumes(source, cancelled=cancelled)


if __name__ == "__main__":
    unittest.main()
