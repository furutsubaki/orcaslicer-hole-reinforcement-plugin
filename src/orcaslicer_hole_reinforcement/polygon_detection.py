"""三角形メッシュから任意方向の正多角形内壁を検出する。"""

import math
from collections.abc import Callable
from dataclasses import dataclass

from .config import HoleReinforcementConfig
from .cylinder_detection import (
    CylinderDetectionCancelled,
    _EPSILON,
    _add,
    _axis_hypotheses,
    _average,
    _canonical_axis,
    _connected_components,
    _dot,
    _edge_triangles,
    _face_normals,
    _length,
    _plane_basis,
    _scale,
    _solve_3x3,
    _subtract,
)
from .detection import HoleShape, MeshSnapshot, PolygonalHoleCandidate, Vector3


class PolygonDetectionCancelled(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _Plane2:
    normal_x: float
    normal_y: float
    offset: float


class PolygonalHoleDetector:
    def detect(
        self,
        mesh: MeshSnapshot,
        config: HoleReinforcementConfig,
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> tuple[PolygonalHoleCandidate, ...]:
        if not any(
            shape in config.enabled_shapes
            for shape in ("hexagon", "octagon", "regular_polygon")
        ):
            return ()

        try:
            normals, valid_triangles = _face_normals(mesh, cancelled)
            edge_triangles = _edge_triangles(mesh, valid_triangles, cancelled)
        except CylinderDetectionCancelled as error:
            raise PolygonDetectionCancelled from error
        axes = _axis_hypotheses(normals, edge_triangles, config.axis_tolerance_deg)
        candidates: list[PolygonalHoleCandidate] = []

        for axis_index, axis in enumerate(axes):
            if axis_index % 64 == 0 and cancelled():
                raise PolygonDetectionCancelled
            maximum_axis_dot = (
                math.sin(math.radians(config.axis_tolerance_deg)) + _EPSILON
            )
            selected = set()
            for triangle_offset, index in enumerate(valid_triangles):
                if triangle_offset % 4096 == 0 and cancelled():
                    raise PolygonDetectionCancelled
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
                    item.shape.value,
                    round(item.center_mm[0], 9),
                    round(item.center_mm[1], 9),
                    round(item.center_mm[2], 9),
                ),
            )
        )


def _fit_component(
    mesh: MeshSnapshot,
    normals: dict[int, Vector3],
    component: tuple[int, ...],
    axis: Vector3,
    config: HoleReinforcementConfig,
) -> PolygonalHoleCandidate | None:
    basis_u, basis_v = _plane_basis(axis)
    planes = _cluster_planes(mesh, normals, component, basis_u, basis_v, config)
    side_count = len(planes)
    shape = _shape_for_side_count(side_count, config)
    if shape is None:
        return None
    planes = tuple(
        sorted(planes, key=lambda plane: math.atan2(plane.normal_y, plane.normal_x))
    )

    center_fit = _fit_center_and_apothem(planes)
    if center_fit is None:
        return None
    center_u, center_v, apothem = center_fit
    if apothem <= _EPSILON:
        return None
    across_flats = apothem * 2.0
    if not config.min_hole_diameter_mm <= across_flats <= config.max_hole_diameter_mm:
        return None

    vertices_2d = tuple(
        _intersect_lines(planes[index], planes[(index + 1) % side_count])
        for index in range(side_count)
    )
    if any(vertex is None for vertex in vertices_2d):
        return None
    cross_section_2d = tuple(vertex for vertex in vertices_2d if vertex is not None)
    edge_lengths = tuple(
        math.dist(cross_section_2d[index], cross_section_2d[(index + 1) % side_count])
        for index in range(side_count)
    )
    mean_edge = sum(edge_lengths) / side_count
    if mean_edge <= _EPSILON:
        return None
    edge_deviation = max(abs(length - mean_edge) for length in edge_lengths) / mean_edge * 100.0
    if edge_deviation > config.polygon_edge_length_tolerance_percent + _EPSILON:
        return None

    expected_angle = (side_count - 2.0) * 180.0 / side_count
    interior_angles = tuple(
        _interior_angle(cross_section_2d, index) for index in range(side_count)
    )
    if any(angle is None for angle in interior_angles):
        return None
    angle_deviation = max(
        abs(angle - expected_angle)
        for angle in interior_angles
        if angle is not None
    )
    if angle_deviation > config.polygon_angle_tolerance_deg + _EPSILON:
        return None

    vertex_indices = {
        vertex for triangle_index in component for vertex in mesh.triangles[triangle_index]
    }
    axial_values = [_dot(mesh.vertices_mm[index], axis) for index in vertex_indices]
    axial_start = min(axial_values)
    axial_end = max(axial_values)
    depth = axial_end - axial_start
    if depth + _EPSILON < config.min_hole_depth_mm:
        return None

    center_on_axis = _add(_scale(basis_u, center_u), _scale(basis_v, center_v))
    midpoint_axial = (axial_start + axial_end) / 2.0
    center = _add(center_on_axis, _scale(axis, midpoint_axial))
    cross_section = tuple(
        _add(
            _add(_scale(basis_u, point[0]), _scale(basis_v, point[1])),
            _scale(axis, midpoint_axial),
        )
        for point in cross_section_2d
    )
    edge_score = _score(
        edge_deviation, config.polygon_edge_length_tolerance_percent
    )
    angle_score = _score(angle_deviation, config.polygon_angle_tolerance_deg)
    return PolygonalHoleCandidate(
        shape=shape,
        side_count=side_count,
        center_mm=center,
        axis=_canonical_axis(axis),
        cross_section_mm=cross_section,
        across_flats_mm=across_flats,
        depth_mm=depth,
        axial_start_mm=axial_start,
        axial_end_mm=axial_end,
        confidence=(edge_score + angle_score) / 2.0,
        triangle_indices=component,
    )


def _shape_for_side_count(
    side_count: int, config: HoleReinforcementConfig
) -> HoleShape | None:
    if side_count == 6 and "hexagon" in config.enabled_shapes:
        return HoleShape.HEXAGON
    if side_count == 8 and "octagon" in config.enabled_shapes:
        return HoleShape.OCTAGON
    if (
        "regular_polygon" in config.enabled_shapes
        and config.min_polygon_sides <= side_count <= config.max_polygon_sides
    ):
        return HoleShape.REGULAR_POLYGON
    return None


def _cluster_planes(
    mesh: MeshSnapshot,
    normals: dict[int, Vector3],
    component: tuple[int, ...],
    basis_u: Vector3,
    basis_v: Vector3,
    config: HoleReinforcementConfig,
) -> tuple[_Plane2, ...]:
    clusters: list[list[tuple[Vector3, float]]] = []
    same_normal = math.cos(math.radians(config.axis_tolerance_deg))
    for triangle_index in component:
        normal = normals[triangle_index]
        centroid = _average(
            tuple(mesh.vertices_mm[index] for index in mesh.triangles[triangle_index])
        )
        offset = _dot(normal, centroid)
        for cluster in clusters:
            reference_normal, reference_offset = cluster[0]
            if (
                _dot(normal, reference_normal) + _EPSILON >= same_normal
                and abs(offset - reference_offset) <= 1e-5
            ):
                cluster.append((normal, offset))
                break
        else:
            clusters.append([(normal, offset)])

    planes = []
    for cluster in clusters:
        normal = _average(tuple(item[0] for item in cluster))
        normal_length = _length(normal)
        if normal_length <= _EPSILON:
            continue
        normal = _scale(normal, 1.0 / normal_length)
        planes.append(
            _Plane2(
                normal_x=_dot(normal, basis_u),
                normal_y=_dot(normal, basis_v),
                offset=sum(item[1] for item in cluster) / len(cluster),
            )
        )
    return tuple(planes)


def _fit_center_and_apothem(planes: tuple[_Plane2, ...]) -> tuple[float, float, float] | None:
    rows = [(plane.normal_x, plane.normal_y, -1.0) for plane in planes]
    normal_matrix = [
        [sum(row[i] * row[j] for row in rows) for j in range(3)] for i in range(3)
    ]
    vector = [
        sum(row[i] * plane.offset for row, plane in zip(rows, planes))
        for i in range(3)
    ]
    return _solve_3x3(normal_matrix, vector)


def _intersect_lines(first: _Plane2, second: _Plane2) -> tuple[float, float] | None:
    determinant = first.normal_x * second.normal_y - first.normal_y * second.normal_x
    if abs(determinant) <= _EPSILON:
        return None
    return (
        (first.offset * second.normal_y - first.normal_y * second.offset) / determinant,
        (first.normal_x * second.offset - first.offset * second.normal_x) / determinant,
    )


def _interior_angle(
    points: tuple[tuple[float, float], ...], index: int
) -> float | None:
    current = points[index]
    previous = points[index - 1]
    following = points[(index + 1) % len(points)]
    first = (previous[0] - current[0], previous[1] - current[1])
    second = (following[0] - current[0], following[1] - current[1])
    divisor = math.hypot(*first) * math.hypot(*second)
    if divisor <= _EPSILON:
        return None
    cosine = max(-1.0, min(1.0, sum(a * b for a, b in zip(first, second)) / divisor))
    return math.degrees(math.acos(cosine))


def _score(deviation: float, tolerance: float) -> float:
    if tolerance <= _EPSILON:
        return 1.0 if deviation <= _EPSILON else 0.0
    return max(0.0, 1.0 - deviation / tolerance)


def _duplicates(
    candidate: PolygonalHoleCandidate,
    existing: list[PolygonalHoleCandidate],
    config: HoleReinforcementConfig,
) -> bool:
    return any(
        candidate.shape is item.shape
        and abs(_dot(candidate.axis, item.axis))
        >= math.cos(math.radians(config.axis_tolerance_deg))
        and abs(candidate.across_flats_mm - item.across_flats_mm) <= 1e-6
        and _length(_subtract(candidate.center_mm, item.center_mm)) <= 1e-6
        for item in existing
    )
