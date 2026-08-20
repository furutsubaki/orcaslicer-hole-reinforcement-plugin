"""穴候補の両端をメッシュトポロジーから分類する。"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from .candidate_detection import HoleCandidate
from .config import HoleReinforcementConfig
from .diagnostics import (
    DiagnosticEvent,
    DiagnosticLevel,
    DiagnosticSink,
    NullDiagnosticSink,
)
from .detection import HoleEndKind, MeshSnapshot, Vector3


_EPSILON = 1e-7


class HoleEndState(Enum):
    OPEN = "open"
    CLOSED = "closed"
    UNCERTAIN = "uncertain"


class HoleEndClassificationCancelled(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ClassifiedHole:
    candidate: HoleCandidate
    start_state: HoleEndState
    end_state: HoleEndState
    end_kind: HoleEndKind | None
    accepted: bool
    reason: str


class HoleEndClassifier:
    def classify(
        self,
        mesh: MeshSnapshot,
        candidates: Iterable[HoleCandidate],
        config: HoleReinforcementConfig,
        *,
        diagnostics: DiagnosticSink = NullDiagnosticSink(),
        cancelled: Callable[[], bool] = lambda: False,
    ) -> tuple[ClassifiedHole, ...]:
        edge_owners = _edge_owners(mesh, cancelled)
        results = []
        for index, candidate in enumerate(candidates):
            if index % 256 == 0 and cancelled():
                raise HoleEndClassificationCancelled
            rims = _candidate_rims(mesh, candidate, edge_owners)
            if rims is None:
                start = end = HoleEndState.UNCERTAIN
            else:
                start = _classify_end(
                    mesh, candidate, rims[0], edge_owners, cancelled
                )
                end = _classify_end(
                    mesh, candidate, rims[1], edge_owners, cancelled
                )
            end_kind, reason = _classify_pair(start, end)
            accepted = end_kind is not None and end_kind.value in config.enabled_end_kinds
            if end_kind is not None and not accepted:
                reason = f"{end_kind.value}_disabled"
            result = ClassifiedHole(candidate, start, end, end_kind, accepted, reason)
            results.append(result)
            emit_classification_diagnostic(result, config, diagnostics)
        return tuple(results)


def emit_classification_diagnostic(
    result: ClassifiedHole,
    config: HoleReinforcementConfig,
    diagnostics: DiagnosticSink,
) -> None:
    if not config.diagnostics_enabled:
        return
    diagnostics.emit(
        DiagnosticEvent(
            DiagnosticLevel.INFO if result.accepted else DiagnosticLevel.WARNING,
            "hole_end_classified"
            if result.end_kind is not None
            else "hole_end_uncertain",
            "穴端を分類しました"
            if result.end_kind is not None
            else "穴端を確定できません",
            {
                **_candidate_diagnostics(result.candidate),
                "start_state": result.start_state.value,
                "end_state": result.end_state.value,
                "end_kind": result.end_kind.value
                if result.end_kind is not None
                else None,
                "accepted": result.accepted,
                "reason": result.reason,
            },
        )
    )


def _candidate_diagnostics(candidate: HoleCandidate) -> dict[str, object]:
    if hasattr(candidate, "radius_mm"):
        shape = "circle"
        diameter = candidate.radius_mm * 2.0
        side_count = None
    else:
        shape = candidate.shape.value
        diameter = candidate.across_flats_mm
        side_count = candidate.side_count
    return {
        "shape": shape,
        "side_count": side_count,
        "diameter_mm": diameter,
        "depth_mm": candidate.depth_mm,
        "center_mm": candidate.center_mm,
        "axis": candidate.axis,
        "confidence": candidate.confidence,
    }


def _edge_owners(
    mesh: MeshSnapshot, cancelled: Callable[[], bool]
) -> dict[tuple[int, int], tuple[int, ...]]:
    owners: dict[tuple[int, int], list[int]] = defaultdict(list)
    for triangle_index, triangle in enumerate(mesh.triangles):
        if triangle_index % 4096 == 0 and cancelled():
            raise HoleEndClassificationCancelled
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            owners[min(first, second), max(first, second)].append(triangle_index)
    return {edge: tuple(indices) for edge, indices in owners.items()}


def _classify_end(
    mesh: MeshSnapshot,
    candidate: HoleCandidate,
    rim_edges: set[tuple[int, int]],
    edge_owners: dict[tuple[int, int], tuple[int, ...]],
    cancelled: Callable[[], bool],
) -> HoleEndState:
    wall_triangles = set(candidate.triangle_indices)
    tolerance = max(_EPSILON, candidate.depth_mm * 1e-7)
    adjacent = set()
    for edge in rim_edges:
        owners = edge_owners.get(edge, ())
        wall_owners = [owner for owner in owners if owner in wall_triangles]
        outer_owners = [owner for owner in owners if owner not in wall_triangles]
        if len(owners) != 2 or len(wall_owners) != 1 or len(outer_owners) != 1:
            return HoleEndState.UNCERTAIN
        adjacent.add(outer_owners[0])

    rim_vertices = _rim_vertices(rim_edges)
    axial_position = sum(
        _dot(mesh.vertices_mm[vertex], candidate.axis)
        for vertex in rim_vertices
    ) / len(rim_vertices)
    endpoint_triangles = _connected_endpoint_triangles(
        mesh,
        adjacent,
        wall_triangles,
        candidate.axis,
        axial_position,
        tolerance,
        edge_owners,
        cancelled,
    )
    center = _endpoint_center(candidate.center_mm, candidate.axis, axial_position)
    if any(
        _triangle_covers_center(mesh, triangle_index, center, candidate.axis, tolerance)
        for triangle_index in endpoint_triangles
    ):
        return HoleEndState.CLOSED
    return HoleEndState.OPEN


def _candidate_rims(
    mesh: MeshSnapshot,
    candidate: HoleCandidate,
    edge_owners: dict[tuple[int, int], tuple[int, ...]],
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]] | None:
    wall_triangles = set(candidate.triangle_indices)
    candidate_edges = set()
    for triangle_index in wall_triangles:
        triangle = mesh.triangles[triangle_index]
        candidate_edges.update(
            (min(first, second), max(first, second))
            for first, second in zip(triangle, triangle[1:] + triangle[:1])
        )
    boundary_edges = {
        edge
        for edge in candidate_edges
        for owners in (edge_owners.get(edge, ()),)
        if sum(owner in wall_triangles for owner in owners) == 1
    }
    vertex_edges: dict[int, set[tuple[int, int]]] = defaultdict(set)
    for edge in boundary_edges:
        for vertex in edge:
            vertex_edges[vertex].add(edge)
    if not boundary_edges or any(len(edges) != 2 for edges in vertex_edges.values()):
        return None

    components = []
    remaining = set(boundary_edges)
    while remaining:
        component = set()
        pending = [remaining.pop()]
        while pending:
            edge = pending.pop()
            component.add(edge)
            for vertex in edge:
                for neighbour in vertex_edges[vertex] & remaining:
                    remaining.remove(neighbour)
                    pending.append(neighbour)
        components.append(component)
    if len(components) != 2:
        return None

    components.sort(
        key=lambda component: sum(
            _dot(mesh.vertices_mm[vertex], candidate.axis)
            for vertex in _rim_vertices(component)
        )
        / len(_rim_vertices(component))
    )
    return components[0], components[1]


def _rim_vertices(edges: set[tuple[int, int]]) -> set[int]:
    return {vertex for edge in edges for vertex in edge}


def _connected_endpoint_triangles(
    mesh: MeshSnapshot,
    seeds: set[int],
    wall_triangles: set[int],
    axis: Vector3,
    axial_position: float,
    tolerance: float,
    edge_owners: dict[tuple[int, int], tuple[int, ...]],
    cancelled: Callable[[], bool],
) -> set[int]:
    endpoint_triangles = set(seeds)
    pending = list(seeds)
    visited_count = 0
    while pending:
        if visited_count % 4096 == 0 and cancelled():
            raise HoleEndClassificationCancelled
        visited_count += 1
        triangle_index = pending.pop()
        triangle = mesh.triangles[triangle_index]
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            edge = (min(first, second), max(first, second))
            for neighbour in edge_owners.get(edge, ()):
                if neighbour in endpoint_triangles or neighbour in wall_triangles:
                    continue
                if all(
                    abs(_dot(mesh.vertices_mm[vertex], axis) - axial_position)
                    <= tolerance
                    for vertex in mesh.triangles[neighbour]
                ):
                    endpoint_triangles.add(neighbour)
                    pending.append(neighbour)
    return endpoint_triangles


def _classify_pair(
    start: HoleEndState, end: HoleEndState
) -> tuple[HoleEndKind | None, str]:
    if HoleEndState.UNCERTAIN in (start, end):
        return None, "incomplete_or_non_manifold_rim"
    if start is HoleEndState.OPEN and end is HoleEndState.OPEN:
        return HoleEndKind.THROUGH, "both_ends_open"
    if {start, end} == {HoleEndState.OPEN, HoleEndState.CLOSED}:
        return HoleEndKind.BLIND, "one_end_closed"
    return None, "both_ends_closed"


def _endpoint_center(center: Vector3, axis: Vector3, axial_position: float) -> Vector3:
    offset = axial_position - _dot(center, axis)
    return tuple(center[index] + axis[index] * offset for index in range(3))


def _triangle_covers_center(
    mesh: MeshSnapshot,
    triangle_index: int,
    center: Vector3,
    axis: Vector3,
    tolerance: float,
) -> bool:
    points = tuple(mesh.vertices_mm[index] for index in mesh.triangles[triangle_index])
    if any(abs(_dot(point, axis) - _dot(center, axis)) > tolerance for point in points):
        return False
    offsets = [tuple(point[index] - center[index] for index in range(3)) for point in points]
    first_edge = tuple(points[1][index] - points[0][index] for index in range(3))
    second_edge = tuple(points[2][index] - points[0][index] for index in range(3))
    triangle_area = abs(_dot(_cross(first_edge, second_edge), axis))
    if triangle_area <= _EPSILON:
        return False
    areas = [
        _dot(_cross(offsets[index], offsets[(index + 1) % 3]), axis)
        for index in range(3)
    ]
    return all(area >= -_EPSILON for area in areas) or all(area <= _EPSILON for area in areas)


def _dot(first: Vector3, second: Vector3) -> float:
    return sum(a * b for a, b in zip(first, second))


def _cross(first: Vector3, second: Vector3) -> Vector3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )
