"""スライスワーカーのモデルから配置後メッシュをコピーする。"""

import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, TypeAlias, TypeVar

from .detection import MeshSnapshot, Triangle, Vector3


Matrix4: TypeAlias = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]
_Row = TypeVar("_Row", Sequence[float], Sequence[int])


class VolumeRole(Enum):
    MODEL_PART = "model_part"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class TransformedVolumeSnapshot:
    print_object_id: int
    model_object_id: int
    volume_id: int
    volume_index: int
    role: VolumeRole
    mesh: MeshSnapshot


class MeshExtractionError(ValueError):
    pass


class MeshExtractionCancelled(Exception):
    pass


class _Mesh(Protocol):
    def vertices(self) -> Sequence[Sequence[float]]: ...

    def triangles(self) -> Sequence[Sequence[int]]: ...


class _Volume(Protocol):
    def id(self) -> int: ...

    def is_model_part(self) -> bool: ...

    def is_negative_volume(self) -> bool: ...

    def matrix(self) -> Sequence[Sequence[float]]: ...

    def mesh(self) -> _Mesh: ...


class _ModelObject(Protocol):
    def id(self) -> int: ...

    def volume_count(self) -> int: ...

    def volume(self, index: int) -> _Volume: ...


class PrintObjectSnapshotSource(Protocol):
    def id(self) -> int: ...

    def model_object(self) -> _ModelObject: ...

    def trafo(self) -> Sequence[Sequence[float]]: ...


def extract_transformed_volumes(
    print_object: PrintObjectSnapshotSource,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[TransformedVolumeSnapshot, ...]:
    """対象PrintObjectの造形座標メッシュをホスト非依存の値へコピーする。"""
    print_object_id = int(print_object.id())
    model_object = print_object.model_object()
    model_object_id = int(model_object.id())
    object_matrix = _copy_matrix(print_object.trafo(), "print object transform")
    snapshots: list[TransformedVolumeSnapshot] = []

    for volume_index in range(model_object.volume_count()):
        if cancelled():
            raise MeshExtractionCancelled

        volume = model_object.volume(volume_index)
        role = _volume_role(volume)
        if role is None:
            continue

        transform = _multiply_matrix(
            object_matrix,
            _copy_matrix(volume.matrix(), f"volume {volume_index} transform"),
        )
        mesh = volume.mesh()
        vertices = tuple(
            _transform_vertex(transform, vertex, volume_index)
            for _, vertex in _cancelable_items(mesh.vertices(), cancelled)
        )
        mirrored = _linear_determinant(transform) < 0.0
        triangles = tuple(
            _copy_triangle(triangle, len(vertices), mirrored, volume_index)
            for _, triangle in _cancelable_items(mesh.triangles(), cancelled)
        )
        snapshots.append(
            TransformedVolumeSnapshot(
                print_object_id=print_object_id,
                model_object_id=model_object_id,
                volume_id=int(volume.id()),
                volume_index=volume_index,
                role=role,
                mesh=MeshSnapshot(vertices_mm=vertices, triangles=triangles),
            )
        )

    return tuple(snapshots)


def _cancelable_items(
    values: Sequence[_Row],
    cancelled: Callable[[], bool],
) -> Iterator[tuple[int, _Row]]:
    for index, value in enumerate(values):
        if index % 4096 == 0 and cancelled():
            raise MeshExtractionCancelled
        yield index, value


def _volume_role(volume: _Volume) -> VolumeRole | None:
    if volume.is_model_part():
        return VolumeRole.MODEL_PART
    if volume.is_negative_volume():
        return VolumeRole.NEGATIVE
    return None


def _copy_matrix(value: Sequence[Sequence[float]], label: str) -> Matrix4:
    if len(value) != 4 or any(len(row) != 4 for row in value):
        raise MeshExtractionError(f"{label} must be a 4x4 matrix")
    matrix = tuple(tuple(float(item) for item in row) for row in value)
    if any(not math.isfinite(item) for row in matrix for item in row):
        raise MeshExtractionError(f"{label} must contain only finite values")
    if any(abs(matrix[3][index]) > 1e-12 for index in range(3)) or not math.isclose(
        matrix[3][3], 1.0, abs_tol=1e-12
    ):
        raise MeshExtractionError(f"{label} must be affine")
    return matrix  # type: ignore[return-value]


def _multiply_matrix(left: Matrix4, right: Matrix4) -> Matrix4:
    return tuple(
        tuple(sum(left[row][item] * right[item][column] for item in range(4)) for column in range(4))
        for row in range(4)
    )  # type: ignore[return-value]


def _transform_vertex(
    matrix: Matrix4, vertex: Sequence[float], volume_index: int
) -> Vector3:
    if len(vertex) != 3:
        raise MeshExtractionError(f"volume {volume_index} vertex must have 3 coordinates")
    source = tuple(float(value) for value in vertex)
    if any(not math.isfinite(value) for value in source):
        raise MeshExtractionError(f"volume {volume_index} vertex must be finite")
    return tuple(
        sum(matrix[row][column] * source[column] for column in range(3))
        + matrix[row][3]
        for row in range(3)
    )  # type: ignore[return-value]


def _linear_determinant(matrix: Matrix4) -> float:
    a, b, c = matrix[0][:3]
    d, e, f = matrix[1][:3]
    g, h, i = matrix[2][:3]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _copy_triangle(
    triangle: Sequence[int], vertex_count: int, mirrored: bool, volume_index: int
) -> Triangle:
    if len(triangle) != 3:
        raise MeshExtractionError(f"volume {volume_index} triangle must have 3 indices")
    copied = tuple(int(index) for index in triangle)
    if any(index < 0 or index >= vertex_count for index in copied):
        raise MeshExtractionError(f"volume {volume_index} triangle index is out of range")
    if mirrored:
        return copied[0], copied[2], copied[1]
    return copied  # type: ignore[return-value]
