"""3D補強領域をレイヤーごとの2D形状へ変換する。"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from .config import HoleReinforcementConfig
from .detection import CylindricalHoleCandidate, Vector3
from .end_classification import ClassifiedHole

Point2: TypeAlias = tuple[float, float]
Polygon2: TypeAlias = tuple[Point2, ...]
_EPSILON = 1e-8


@dataclass(frozen=True, slots=True)
class PlanarRegion:
    contour_mm: Polygon2
    holes_mm: tuple[Polygon2, ...] = ()


RegionSet: TypeAlias = tuple[PlanarRegion, ...]


@dataclass(frozen=True, slots=True)
class LayerHoleContour:
    hole_index: int
    contour_mm: Polygon2


@dataclass(frozen=True, slots=True)
class LayerPlane:
    index: int
    print_z_mm: float
    model_regions: RegionSet = ()
    hole_contours: tuple[LayerHoleContour, ...] = ()


@dataclass(frozen=True, slots=True)
class ReinforcementRegion:
    layer_index: int
    regions: RegionSet


class PlanarGeometry(Protocol):
    def difference(self, subject: RegionSet, clips: RegionSet) -> RegionSet: ...
    def intersection(self, subject: RegionSet, clips: RegionSet) -> RegionSet: ...
    def offset(self, regions: RegionSet, distance_mm: float) -> RegionSet: ...
    def union(self, regions: RegionSet) -> RegionSet: ...


class ReinforcementPlanningCancelled(Exception):
    pass


class ReinforcementVolumeSlicer:
    def __init__(self, geometry: PlanarGeometry, *, circle_segments: int = 64):
        if circle_segments < 12:
            raise ValueError("circle_segments must be at least 12")
        self._geometry = geometry
        self._circle_segments = circle_segments

    def plan(
        self,
        holes: Sequence[ClassifiedHole],
        layers: Sequence[LayerPlane],
        config: HoleReinforcementConfig,
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> tuple[ReinforcementRegion, ...]:
        if not config.solid_reinforcement:
            return ()
        profiles = tuple(
            _prism_profiles(hole, config.reinforcement_width_mm, self._circle_segments)
            if hole.accepted
            else None
            for hole in holes
        )
        regions = []
        for layer_offset, layer in enumerate(layers):
            if layer_offset % 256 == 0 and cancelled():
                raise ReinforcementPlanningCancelled
            if not layer.model_regions:
                continue
            overrides = {
                contour.hole_index: contour.contour_mm for contour in layer.hole_contours
            }
            layer_regions = []
            for hole_index, profile in enumerate(profiles):
                if hole_index % 256 == 0 and cancelled():
                    raise ReinforcementPlanningCancelled
                if profile is None:
                    continue
                (
                    inner_profile,
                    outer_profile,
                    axis,
                    axial_start,
                    axial_end,
                    tangent_z_bounds,
                ) = profile
                if tangent_z_bounds is not None and (
                    layer.print_z_mm <= tangent_z_bounds[0] + _EPSILON
                    or layer.print_z_mm >= tangent_z_bounds[1] - _EPSILON
                ):
                    continue
                outer = _slice_prism(
                    outer_profile, axis, axial_start, axial_end, layer.print_z_mm
                )
                if outer is None:
                    continue
                override = overrides.get(hole_index)
                if override is not None and _valid_polygon(override):
                    expanded_override = self._geometry.offset(
                        (PlanarRegion(override),), config.reinforcement_width_mm
                    )
                    subject = self._geometry.union(
                        (PlanarRegion(outer), *expanded_override)
                    )
                    inner = override
                else:
                    subject = (PlanarRegion(outer),)
                    inner = _slice_prism(
                        inner_profile,
                        axis,
                        axial_start,
                        axial_end,
                        layer.print_z_mm,
                    )
                clips = (PlanarRegion(inner),) if inner is not None else ()
                layer_regions.extend(self._geometry.difference(subject, clips))
            if not layer_regions:
                continue
            combined = self._geometry.union(tuple(layer_regions))
            clipped = self._geometry.intersection(combined, layer.model_regions)
            if clipped:
                regions.append(ReinforcementRegion(layer.index, clipped))
        return tuple(regions)


def _prism_profiles(
    hole: ClassifiedHole, width_mm: float, circle_segments: int
) -> tuple[
    tuple[Vector3, ...],
    tuple[Vector3, ...],
    Vector3,
    float,
    float,
    tuple[float, float] | None,
]:
    candidate = hole.candidate
    if isinstance(candidate, CylindricalHoleCandidate):
        basis_u, basis_v = _plane_basis(candidate.axis)
        profile_radius = candidate.radius_mm / math.cos(math.pi / circle_segments)
        inner = tuple(
            _add(
                candidate.center_mm,
                _add(
                    _scale(basis_u, profile_radius * math.cos(angle)),
                    _scale(basis_v, profile_radius * math.sin(angle)),
                ),
            )
            for angle in (
                2.0 * math.pi * index / circle_segments
                for index in range(circle_segments)
            )
        )
        scale = (candidate.radius_mm + width_mm) / candidate.radius_mm
        radial_z = (candidate.radius_mm + width_mm) * math.sqrt(
            max(0.0, 1.0 - candidate.axis[2] ** 2)
        )
        if radial_z > _EPSILON:
            endpoint_z = tuple(
                _move_to_axial(candidate.center_mm, candidate.axis, position)[2]
                for position in (
                    candidate.axial_start_mm,
                    candidate.axial_end_mm,
                )
            )
            tangent_z_bounds = (
                min(endpoint_z) - radial_z,
                max(endpoint_z) + radial_z,
            )
        else:
            tangent_z_bounds = None
    else:
        inner = candidate.cross_section_mm
        scale = (candidate.across_flats_mm / 2.0 + width_mm) / (
            candidate.across_flats_mm / 2.0
        )
        tangent_z_bounds = None
    outer = tuple(
        _add(candidate.center_mm, _scale(_subtract(point, candidate.center_mm), scale))
        for point in inner
    )
    return (
        inner,
        outer,
        candidate.axis,
        candidate.axial_start_mm,
        candidate.axial_end_mm,
        tangent_z_bounds,
    )


def _slice_prism(
    profile: tuple[Vector3, ...],
    axis: Vector3,
    axial_start: float,
    axial_end: float,
    print_z_mm: float,
) -> Polygon2 | None:
    if axial_end <= axial_start:
        raise ValueError("invalid prism depth")
    lower = tuple(_move_to_axial(point, axis, axial_start) for point in profile)
    upper = tuple(_move_to_axial(point, axis, axial_end) for point in profile)
    vertices = (*lower, *upper)
    side_count = len(profile)
    edges = []
    for offset in (0, side_count):
        edges.extend(
            (offset + index, offset + (index + 1) % side_count)
            for index in range(side_count)
        )
    edges.extend((index, side_count + index) for index in range(side_count))

    points = []
    for first_index, second_index in edges:
        first = vertices[first_index]
        second = vertices[second_index]
        first_distance = first[2] - print_z_mm
        second_distance = second[2] - print_z_mm
        if abs(first_distance) <= _EPSILON:
            points.append((first[0], first[1]))
        if abs(second_distance) <= _EPSILON:
            points.append((second[0], second[1]))
        if first_distance * second_distance < -_EPSILON:
            ratio = first_distance / (first_distance - second_distance)
            points.append(
                (
                    first[0] + (second[0] - first[0]) * ratio,
                    first[1] + (second[1] - first[1]) * ratio,
                )
            )
    polygon = _convex_hull(points)
    return polygon if _valid_polygon(polygon) else None


def _move_to_axial(point: Vector3, axis: Vector3, position: float) -> Vector3:
    return _add(point, _scale(axis, position - _dot(point, axis)))


def _convex_hull(points: Sequence[Point2]) -> Polygon2:
    unique = sorted(set(points))
    if len(unique) < 3:
        return tuple(unique)

    def cross(origin: Point2, first: Point2, second: Point2) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= _EPSILON:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= _EPSILON:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def _valid_polygon(polygon: Polygon2) -> bool:
    if len(polygon) < 3:
        return False
    area = abs(
        sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in zip(polygon, polygon[1:] + polygon[:1])
        )
    ) / 2.0
    return area > _EPSILON


def _plane_basis(axis: Vector3) -> tuple[Vector3, Vector3]:
    reference = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    first = _normalize(_cross(axis, reference))
    return first, _cross(axis, first)


def _normalize(vector: Vector3) -> Vector3:
    return _scale(vector, 1.0 / math.sqrt(_dot(vector, vector)))


def _add(first: Vector3, second: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(first, second))


def _subtract(first: Vector3, second: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(first, second))


def _scale(vector: Vector3, factor: float) -> Vector3:
    return tuple(value * factor for value in vector)


def _dot(first: Vector3, second: Vector3) -> float:
    return sum(a * b for a, b in zip(first, second))


def _cross(first: Vector3, second: Vector3) -> Vector3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


class ReinforcementPlanner(Protocol):
    def plan(
        self,
        holes: Sequence[ClassifiedHole],
        layers: Sequence[LayerPlane],
        config: HoleReinforcementConfig,
    ) -> Sequence[ReinforcementRegion]: ...
