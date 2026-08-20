"""三角形メッシュから任意方向の円柱内壁を検出する。"""

import math
from collections import defaultdict, deque
from collections.abc import Callable

from .config import HoleReinforcementConfig
from .detection import CylindricalHoleCandidate, MeshSnapshot, Vector3


_EPSILON = 1e-9


class CylinderDetectionCancelled(Exception):
    pass


class CylindricalHoleDetector:
    def detect(
        self,
        mesh: MeshSnapshot,
        config: HoleReinforcementConfig,
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> tuple[CylindricalHoleCandidate, ...]:
        if "circle" not in config.enabled_shapes:
            return ()

        normals, valid_triangles = _face_normals(mesh, cancelled)
        edge_triangles = _edge_triangles(mesh, valid_triangles, cancelled)
        axes = _axis_hypotheses(normals, edge_triangles, config.axis_tolerance_deg)
        candidates: list[CylindricalHoleCandidate] = []

        for axis_index, axis in enumerate(axes):
            if axis_index % 64 == 0 and cancelled():
                raise CylinderDetectionCancelled
            selected = set()
            maximum_axis_dot = (
                math.sin(math.radians(config.axis_tolerance_deg)) + _EPSILON
            )
            for triangle_offset, index in enumerate(valid_triangles):
                if triangle_offset % 4096 == 0 and cancelled():
                    raise CylinderDetectionCancelled
                if abs(_dot(normals[index], axis)) <= maximum_axis_dot:
                    selected.add(index)
            for component in _connected_components(selected, edge_triangles):
                candidate = _fit_component(mesh, normals, component, axis, config)
                if candidate is not None and not _duplicates(candidate, candidates, config):
                    candidates.append(candidate)

        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    round(item.center_mm[0], 9),
                    round(item.center_mm[1], 9),
                    round(item.center_mm[2], 9),
                    item.radius_mm,
                ),
            )
        )


def _face_normals(
    mesh: MeshSnapshot, cancelled: Callable[[], bool]
) -> tuple[dict[int, Vector3], set[int]]:
    normals: dict[int, Vector3] = {}
    for index, triangle in enumerate(mesh.triangles):
        if index % 4096 == 0 and cancelled():
            raise CylinderDetectionCancelled
        first, second, third = (mesh.vertices_mm[item] for item in triangle)
        normal = _cross(_subtract(second, first), _subtract(third, first))
        length = _length(normal)
        if length > _EPSILON:
            normals[index] = _scale(normal, 1.0 / length)
    return normals, set(normals)


def _edge_triangles(
    mesh: MeshSnapshot,
    valid_triangles: set[int],
    cancelled: Callable[[], bool],
) -> dict[tuple[int, int], tuple[int, ...]]:
    owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for triangle_offset, index in enumerate(valid_triangles):
        if triangle_offset % 4096 == 0 and cancelled():
            raise CylinderDetectionCancelled
        triangle = mesh.triangles[index]
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            owners[min(first, second), max(first, second)].append(index)
    return {edge: tuple(indices) for edge, indices in owners.items()}


def _axis_hypotheses(
    normals: dict[int, Vector3],
    edge_triangles: dict[tuple[int, int], tuple[int, ...]],
    tolerance_deg: float,
) -> tuple[Vector3, ...]:
    axes: list[Vector3] = []
    same_axis = math.cos(math.radians(max(tolerance_deg, 0.1)))
    for owners in edge_triangles.values():
        if len(owners) != 2:
            continue
        cross = _cross(normals[owners[0]], normals[owners[1]])
        length = _length(cross)
        if length <= _EPSILON:
            continue
        axis = _canonical_axis(_scale(cross, 1.0 / length))
        if all(abs(_dot(axis, existing)) < same_axis for existing in axes):
            axes.append(axis)
    return tuple(axes)


def _connected_components(
    selected: set[int], edge_triangles: dict[tuple[int, int], tuple[int, ...]]
) -> tuple[tuple[int, ...], ...]:
    neighbours: dict[int, set[int]] = defaultdict(set)
    for owners in edge_triangles.values():
        selected_owners = [owner for owner in owners if owner in selected]
        for first in selected_owners:
            neighbours[first].update(second for second in selected_owners if second != first)

    remaining = set(selected)
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        queue = deque((start,))
        while queue:
            current = queue.popleft()
            additions = neighbours[current] & remaining
            remaining.difference_update(additions)
            component.update(additions)
            queue.extend(additions)
        components.append(tuple(sorted(component)))
    return tuple(components)


def _fit_component(
    mesh: MeshSnapshot,
    normals: dict[int, Vector3],
    component: tuple[int, ...],
    axis: Vector3,
    config: HoleReinforcementConfig,
) -> CylindricalHoleCandidate | None:
    vertex_indices = sorted(
        {vertex for triangle_index in component for vertex in mesh.triangles[triangle_index]}
    )
    if len(vertex_indices) < 6:
        return None

    basis_u, basis_v = _plane_basis(axis)
    projected = [
        (_dot(mesh.vertices_mm[index], basis_u), _dot(mesh.vertices_mm[index], basis_v))
        for index in vertex_indices
    ]
    circle = _fit_circle(projected)
    if circle is None:
        return None
    center_u, center_v, radius = circle
    residuals = [abs(math.hypot(x - center_u, y - center_v) - radius) for x, y in projected]
    maximum_residual = max(residuals)
    if maximum_residual > config.circle_radial_tolerance_mm + _EPSILON:
        return None

    diameter = radius * 2.0
    if not config.min_hole_diameter_mm <= diameter <= config.max_hole_diameter_mm:
        return None
    if not _covers_full_circle(projected, center_u, center_v):
        return None

    axial_values = [_dot(mesh.vertices_mm[index], axis) for index in vertex_indices]
    axial_start = min(axial_values)
    axial_end = max(axial_values)
    depth = axial_end - axial_start
    if depth + _EPSILON < config.min_hole_depth_mm:
        return None

    center_on_axis = _add(_scale(basis_u, center_u), _scale(basis_v, center_v))
    midpoint = _add(center_on_axis, _scale(axis, (axial_start + axial_end) / 2.0))
    orientation_scores = []
    for triangle_index in component:
        triangle_center = _average(
            tuple(mesh.vertices_mm[index] for index in mesh.triangles[triangle_index])
        )
        radial = _subtract(
            triangle_center,
            _add(center_on_axis, _scale(axis, _dot(triangle_center, axis))),
        )
        radial_length = _length(radial)
        if radial_length > _EPSILON:
            orientation_scores.append(_dot(normals[triangle_index], radial) / radial_length)
    if not orientation_scores or sum(orientation_scores) / len(orientation_scores) >= -0.5:
        return None

    tolerance = max(config.circle_radial_tolerance_mm, 1e-6)
    fit_score = max(0.0, 1.0 - maximum_residual / tolerance)
    orientation_score = min(1.0, -sum(orientation_scores) / len(orientation_scores))
    return CylindricalHoleCandidate(
        center_mm=midpoint,
        axis=axis,
        radius_mm=radius,
        depth_mm=depth,
        axial_start_mm=axial_start,
        axial_end_mm=axial_end,
        confidence=(fit_score + orientation_score) / 2.0,
        triangle_indices=component,
    )


def _fit_circle(points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    rows = [(x, y, 1.0) for x, y in points]
    right = [-(x * x + y * y) for x, y in points]
    normal = [[sum(row[i] * row[j] for row in rows) for j in range(3)] for i in range(3)]
    vector = [sum(row[i] * value for row, value in zip(rows, right)) for i in range(3)]
    solution = _solve_3x3(normal, vector)
    if solution is None:
        return None
    coefficient_x, coefficient_y, constant = solution
    center_x = -coefficient_x / 2.0
    center_y = -coefficient_y / 2.0
    radius_squared = center_x * center_x + center_y * center_y - constant
    if radius_squared <= _EPSILON:
        return None
    return center_x, center_y, math.sqrt(radius_squared)


def _solve_3x3(matrix: list[list[float]], vector: list[float]) -> tuple[float, float, float] | None:
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= _EPSILON:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column])
            ]
    return tuple(row[3] for row in augmented)  # type: ignore[return-value]


def _covers_full_circle(
    points: list[tuple[float, float]], center_x: float, center_y: float
) -> bool:
    angles = sorted({round(math.atan2(y - center_y, x - center_x), 12) for x, y in points})
    if len(angles) < 6:
        return False
    gaps = [second - first for first, second in zip(angles, angles[1:])]
    gaps.append(angles[0] + 2.0 * math.pi - angles[-1])
    ordered = sorted(gaps)
    median = ordered[len(ordered) // 2]
    return max(gaps) <= median * 1.75 + 1e-7


def _duplicates(
    candidate: CylindricalHoleCandidate,
    existing: list[CylindricalHoleCandidate],
    config: HoleReinforcementConfig,
) -> bool:
    return any(
        abs(_dot(candidate.axis, item.axis))
        >= math.cos(math.radians(config.axis_tolerance_deg))
        and abs(candidate.radius_mm - item.radius_mm) <= config.circle_radial_tolerance_mm
        and _length(_subtract(candidate.center_mm, item.center_mm))
        <= max(config.circle_radial_tolerance_mm, 1e-6)
        for item in existing
    )


def _plane_basis(axis: Vector3) -> tuple[Vector3, Vector3]:
    reference = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    first = _normalize(_cross(axis, reference))
    return first, _cross(axis, first)


def _canonical_axis(axis: Vector3) -> Vector3:
    for value in axis:
        if abs(value) > _EPSILON:
            return axis if value > 0.0 else _scale(axis, -1.0)
    return axis


def _average(values: tuple[Vector3, ...]) -> Vector3:
    return tuple(sum(value[index] for value in values) / len(values) for index in range(3))  # type: ignore[return-value]


def _add(first: Vector3, second: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(first, second))  # type: ignore[return-value]


def _subtract(first: Vector3, second: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(first, second))  # type: ignore[return-value]


def _scale(vector: Vector3, factor: float) -> Vector3:
    return tuple(value * factor for value in vector)  # type: ignore[return-value]


def _dot(first: Vector3, second: Vector3) -> float:
    return sum(a * b for a, b in zip(first, second))


def _cross(first: Vector3, second: Vector3) -> Vector3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _length(vector: Vector3) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: Vector3) -> Vector3:
    return _scale(vector, 1.0 / _length(vector))
