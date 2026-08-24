"""issue 01の検証マトリクスから決定的なASCII STL群を生成する。"""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "test-models" / "fixtures"
ANGLES = (0.0, 30.0, 45.0, 60.0, 90.0)
SHAPES = {"circle": 96, "hexagon": 6, "octagon": 8}
MATRIX_MARGIN_MM = 8.0
_MATRIX_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class FixtureCase:
    case_id: str
    shape: str
    angle_deg: float
    diameter_mm: float
    depth_mm: float
    start: str
    end: str
    expected: str = "accepted"
    reason: str | None = None
    inward: bool = True
    covered_sides: int | None = None
    radial_scales: tuple[float, ...] | None = None
    secondary_radius_scale: float = 1.0
    config: tuple[tuple[str, float], ...] = ()
    dimension_tolerance_mm: float = 1e-6

    @property
    def axis(self) -> tuple[float, float, float]:
        radians = math.radians(self.angle_deg)
        return math.cos(radians), 0.0, math.sin(radians)

    @property
    def end_kind(self) -> str | None:
        if self.expected != "accepted":
            return None
        return "through" if self.start == self.end == "open" else "blind"

    @property
    def printable(self) -> bool:
        return self.case_id not in ("negative-open-groove", "negative-broken-mesh")


def cases() -> tuple[FixtureCase, ...]:
    matrix = [
        FixtureCase(
            f"matrix-{shape}-{end_kind}-{angle:g}",
            shape,
            angle,
            4.0,
            12.0,
            "open",
            "open" if end_kind == "through" else "closed",
        )
        for angle in ANGLES
        for shape in SHAPES
        for end_kind in ("through", "blind")
    ]
    direction_boundaries = [
        FixtureCase(f"direction-circle-through-{angle:g}", "circle", angle, 4.0, 12.0, "open", "open")
        for angle in (0.1, 89.9)
    ]
    dimension_boundaries = [
        FixtureCase("diameter-below-min", "circle", 90.0, 2.99, 12.0, "open", "open", "not_detected"),
        FixtureCase("diameter-at-min", "circle", 90.0, 3.0, 12.0, "open", "open"),
        FixtureCase("diameter-at-max", "circle", 90.0, 10.0, 12.0, "open", "open"),
        FixtureCase("diameter-above-max", "circle", 90.0, 10.01, 12.0, "open", "open", "not_detected"),
        FixtureCase("depth-below-min", "circle", 90.0, 4.0, 1.99, "open", "open", "not_detected"),
        FixtureCase("depth-at-min", "circle", 90.0, 4.0, 2.0, "open", "open"),
    ]
    circle_scales = tuple(1.05 if index % 2 else 1.0 for index in range(96))
    circle_residual = 0.05060966544098777
    shape_boundaries = [
        FixtureCase("circle-tolerance-inside", "circle", 90.0, 4.0, 12.0, "open", "open", radial_scales=circle_scales, config=(("circle_radial_tolerance_mm", circle_residual + 0.01),), dimension_tolerance_mm=0.2),
        FixtureCase("circle-tolerance-at", "circle", 90.0, 4.0, 12.0, "open", "open", radial_scales=circle_scales, config=(("circle_radial_tolerance_mm", circle_residual),), dimension_tolerance_mm=0.2),
        FixtureCase("circle-tolerance-outside", "circle", 90.0, 4.0, 12.0, "open", "open", "not_detected", radial_scales=circle_scales, config=(("circle_radial_tolerance_mm", circle_residual - 0.01),)),
        FixtureCase("polygon-edge-tolerance-inside", "hexagon", 90.0, 4.0, 12.0, "open", "open", radial_scales=(1.05, 1.0, 1.0, 1.0, 1.0, 1.0), config=(("polygon_edge_length_tolerance_percent", 1.8128196293633158), ("polygon_angle_tolerance_deg", 15.0)), dimension_tolerance_mm=0.2),
        FixtureCase("polygon-edge-tolerance-at", "hexagon", 90.0, 4.0, 12.0, "open", "open", radial_scales=(1.05, 1.0, 1.0, 1.0, 1.0, 1.0), config=(("polygon_edge_length_tolerance_percent", 1.7128196293633158), ("polygon_angle_tolerance_deg", 15.0)), dimension_tolerance_mm=0.2),
        FixtureCase("polygon-edge-tolerance-outside", "hexagon", 90.0, 4.0, 12.0, "open", "open", "not_detected", radial_scales=(1.05, 1.0, 1.0, 1.0, 1.0, 1.0), config=(("polygon_edge_length_tolerance_percent", 1.6128196293633157), ("polygon_angle_tolerance_deg", 15.0))),
        FixtureCase("polygon-angle-tolerance-inside", "hexagon", 90.0, 4.0, 12.0, "open", "open", radial_scales=(1.02, 1.0, 1.0, 1.0, 1.0, 1.0), config=(("polygon_edge_length_tolerance_percent", 25.0), ("polygon_angle_tolerance_deg", 2.0649400883560643)), dimension_tolerance_mm=0.2),
        FixtureCase("polygon-angle-tolerance-at", "hexagon", 90.0, 4.0, 12.0, "open", "open", radial_scales=(1.02, 1.0, 1.0, 1.0, 1.0, 1.0), config=(("polygon_edge_length_tolerance_percent", 25.0), ("polygon_angle_tolerance_deg", 1.9649400883560642)), dimension_tolerance_mm=0.2),
        FixtureCase("polygon-angle-tolerance-outside", "hexagon", 90.0, 4.0, 12.0, "open", "open", "not_detected", radial_scales=(1.02, 1.0, 1.0, 1.0, 1.0, 1.0), config=(("polygon_edge_length_tolerance_percent", 25.0), ("polygon_angle_tolerance_deg", 1.8649400883560643))),
    ]
    negatives = [
        FixtureCase("negative-outer-cylinder", "circle", 90.0, 4.0, 12.0, "open", "open", "not_detected", inward=False),
        FixtureCase("negative-open-groove", "circle", 90.0, 4.0, 12.0, "broken", "broken", "not_detected", covered_sides=72),
        FixtureCase("negative-ellipse", "circle", 90.0, 4.0, 12.0, "open", "open", "not_detected", secondary_radius_scale=1.15),
        FixtureCase("negative-irregular-hexagon", "hexagon", 90.0, 4.0, 12.0, "open", "open", "not_detected", radial_scales=(1.2, 1.0, 1.0, 1.0, 1.0, 1.0)),
        FixtureCase("negative-internal-cavity", "octagon", 90.0, 4.0, 12.0, "closed", "closed", "rejected", "both_ends_closed"),
        FixtureCase("negative-broken-mesh", "octagon", 90.0, 4.0, 12.0, "open", "broken", "rejected", "incomplete_or_non_manifold_rim"),
    ]
    return tuple((*matrix, *direction_boundaries, *dimension_boundaries, *shape_boundaries, *negatives))


def build_mesh(case: FixtureCase):
    if case.case_id.startswith("matrix-"):
        return _build_matrix_fixture(case)
    sides = SHAPES[case.shape]
    axis = case.axis
    reference = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    basis_u = _normalize(_cross(axis, reference))
    basis_v = _cross(axis, basis_u)
    radius = case.diameter_mm / 2.0
    if case.shape != "circle":
        radius /= math.cos(math.pi / sides)
    scales = case.radial_scales or (1.0,) * sides
    ring_count = sides if case.covered_sides is None else case.covered_sides + 1
    vertices = []
    for axial in (-case.depth_mm / 2.0, case.depth_mm / 2.0):
        for index in range(ring_count):
            angle = 2.0 * math.pi * index / sides
            vertices.append(
                tuple(
                    axis[coordinate] * axial
                    + scales[index % sides]
                    * radius
                    * (
                        basis_u[coordinate] * math.cos(angle)
                        + case.secondary_radius_scale
                        * basis_v[coordinate]
                        * math.sin(angle)
                    )
                    for coordinate in range(3)
                )
            )
    triangles = []
    face_count = sides if case.covered_sides is None else case.covered_sides
    for index in range(face_count):
        following = (index + 1) % ring_count
        lower = (index, following)
        upper = (ring_count + index, ring_count + following)
        outward = ((lower[0], lower[1], upper[1]), (lower[0], upper[1], upper[0]))
        triangles.extend(
            tuple(reversed(triangle)) if case.inward else triangle
            for triangle in outward
        )
    if case.covered_sides is None:
        if not case.inward and case.start != "broken" and case.end != "broken":
            _add_disk(vertices, triangles, tuple(range(sides)))
            _add_disk(vertices, triangles, tuple(range(sides, sides * 2)))
        elif case.inward and case.start != "broken" and case.end != "broken":
            _close_printable_fixture(
                vertices,
                triangles,
                case,
                basis_u,
                basis_v,
                radius,
                scales,
            )
        else:
            for level, end in ((0, case.start), (1, case.end)):
                _add_end(vertices, triangles, tuple(level * sides + i for i in range(sides)), end)
    return tuple(vertices), tuple(triangles)


def _hole_basis(axis):
    reference = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    basis_u = _normalize(_cross(axis, reference))
    return basis_u, _cross(axis, basis_u)


def _hole_radius(case, sides):
    radius = case.diameter_mm / 2.0
    if case.shape != "circle":
        radius /= math.cos(math.pi / sides)
    return radius


def _hole_offsets(case, sides, basis_u, basis_v, radius, scales):
    """穴の各稜線が通る、中心線からのオフセット。"""
    offsets = []
    for index in range(sides):
        angle = 2.0 * math.pi * index / sides
        offsets.append(
            tuple(
                scales[index] * radius
                * (
                    basis_u[coordinate] * math.cos(angle)
                    + case.secondary_radius_scale * basis_v[coordinate] * math.sin(angle)
                )
                for coordinate in range(3)
            )
        )
    return tuple(offsets)


def _cut_rim(offsets, axis, primary, plane):
    """穴の稜線を、主軸に垂直な平面で切った開口多角形。"""
    rim = []
    for offset in offsets:
        along = (plane - offset[primary]) / axis[primary]
        point = [offset[c] + along * axis[c] for c in range(3)]
        # 丸め誤差で開口が面をわずかに突き抜けると、外形の隅が最外周でなくなる。
        point[primary] = plane
        rim.append(tuple(point))
    return tuple(rim)


def _offset_rim(offsets, axis, along):
    return tuple(
        tuple(offset[c] + along * axis[c] for c in range(3)) for offset in offsets
    )


def matrix_geometry(case):
    """軸整列の直方体と、それを貫く傾斜穴のリムを決める。

    穴が抜ける主軸は、水平穴だけX、それ以外はZにする。こうすると外形が板状になり、
    第1レイヤがプレートへ面で接触する。
    """
    sides = SHAPES[case.shape]
    axis = case.axis
    basis_u, basis_v = _hole_basis(axis)
    radius = _hole_radius(case, sides)
    scales = case.radial_scales or (1.0,) * sides
    offsets = _hole_offsets(case, sides, basis_u, basis_v, radius, scales)

    primary = 2 if abs(axis[2]) > _MATRIX_EPSILON else 0

    if case.end_kind == "through":
        # 中心線が直方体を貫く長さがちょうどdepth_mmになる位置で切る。
        half = case.depth_mm / 2.0 * abs(axis[primary])
        rims = (
            _cut_rim(offsets, axis, primary, -half),
            _cut_rim(offsets, axis, primary, half),
        )
        primary_bounds = (-half, half)
    else:
        # 開口を主軸の正側に置き、そこからdepth_mmだけ掘る。
        opening = _cut_rim(offsets, axis, primary, 0.0)
        bottom = _offset_rim(offsets, axis, -case.depth_mm)
        rims = (opening, bottom)
        floor = min(point[primary] for point in bottom) - MATRIX_MARGIN_MM
        primary_bounds = (floor, 0.0)

    rim_points = [point for rim in rims for point in rim]
    bounds = []
    for coordinate in range(3):
        if coordinate == primary:
            bounds.append(primary_bounds)
            continue
        span = [point[coordinate] for point in rim_points]
        bounds.append(
            (min(span) - MATRIX_MARGIN_MM, max(span) + MATRIX_MARGIN_MM)
        )
    return sides, primary, rims, tuple(bounds)


def _plane_axes(primary):
    return tuple(coordinate for coordinate in range(3) if coordinate != primary)


def _corner_point(key, bounds):
    return tuple(bounds[coordinate][key[coordinate]] for coordinate in range(3))


def _face_corner_keys(coordinate, positive):
    """面内で反時計回り（外向き法線）に並べた4隅のキー。"""
    axis_a, axis_b = _plane_axes(coordinate)
    keys = []
    for value_a, value_b in ((0, 0), (1, 0), (1, 1), (0, 1)):
        key = [0, 0, 0]
        key[coordinate] = 1 if positive else 0
        key[axis_a] = value_a
        key[axis_b] = value_b
        keys.append(tuple(key))
    return tuple(keys)


def _append_points(vertices, points):
    start = len(vertices)
    vertices.extend(points)
    return tuple(range(start, len(vertices)))


def _fill_holed_face(triangles, rim, rim_points, corners, corner_points, primary, flip):
    """矩形の面に開口を1つ持つ領域を、内周と4隅だけで三角形分割する。

    矩形の辺を分割しないので、隣接する面とエッジが一致し2多様体を保てる。
    """
    axis_a, axis_b = _plane_axes(primary)
    center_a = sum(point[axis_a] for point in rim_points) / len(rim_points)
    center_b = sum(point[axis_b] for point in rim_points) / len(rim_points)

    events = []
    for index, point in enumerate(rim_points):
        angle = math.atan2(point[axis_b] - center_b, point[axis_a] - center_a)
        events.append((angle, 0, index))
    for index, point in enumerate(corner_points):
        angle = math.atan2(point[axis_b] - center_b, point[axis_a] - center_a)
        events.append((angle, 1, index))
    events.sort()

    at_rim = events[max(i for i, e in enumerate(events) if e[1] == 0)][2]
    at_corner = events[max(i for i, e in enumerate(events) if e[1] == 1)][2]

    for _angle, kind, index in events:
        if kind == 0:
            triangle = (rim[at_rim], corners[at_corner], rim[index])
            at_rim = index
        else:
            triangle = (corners[at_corner], corners[index], rim[at_rim])
            at_corner = index
        triangles.append(tuple(reversed(triangle)) if flip else triangle)


def _add_plain_face(triangles, box, coordinate, positive):
    corners = tuple(box[key] for key in _face_corner_keys(coordinate, positive))
    faces = ((corners[0], corners[1], corners[2]), (corners[0], corners[2], corners[3]))
    for triangle in faces:
        triangles.append(triangle if positive else tuple(reversed(triangle)))


def _add_box_corners(vertices, bounds):
    """直方体の8隅を1度だけ作り、面どうしでエッジを共有できるようにする。"""
    box = {}
    for key in ((x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)):
        (index,) = _append_points(vertices, (_corner_point(key, bounds),))
        box[key] = index
    return box


def _add_hole_wall(triangles, near_rim, far_rim):
    for index in range(len(near_rim)):
        following = (index + 1) % len(near_rim)
        triangles.append((near_rim[index], far_rim[index], far_rim[following]))
        triangles.append((near_rim[index], far_rim[following], near_rim[following]))


def _add_hole_floor(vertices, triangles, rim, rim_points):
    center = tuple(
        sum(point[coordinate] for point in rim_points) / len(rim_points)
        for coordinate in range(3)
    )
    (center_index,) = _append_points(vertices, (center,))
    for index in range(len(rim)):
        following = (index + 1) % len(rim)
        triangles.append((center_index, rim[following], rim[index]))


def _build_matrix_fixture(case):
    """外形を軸整列の直方体にし、穴だけを傾ける。

    外形まで穴の軸で作るとブロックごと傾き、プレートへ線接触して造形できない。
    """
    _sides, primary, rims, bounds = matrix_geometry(case)
    vertices = []
    triangles = []

    # 穴の壁面頂点を先頭に置く規約は、深さの実測と余白テストが前提にしている。
    rim_indices = [_append_points(vertices, rim) for rim in rims]
    through = case.end_kind == "through"
    # 止まり穴はrims[0]が開口（主軸の正側）でrims[1]が底になり、貫通穴と前後が逆。
    # 揃えないと壁面の法線が外を向き、円筒として検出されなくなる。
    if through:
        _add_hole_wall(triangles, rim_indices[0], rim_indices[1])
    else:
        _add_hole_wall(triangles, rim_indices[1], rim_indices[0])

    box = _add_box_corners(vertices, bounds)
    opening_faces = ((0, False), (1, True)) if through else ((0, True),)
    opened = set()
    for rim_position, positive in opening_faces:
        keys = _face_corner_keys(primary, positive)
        _fill_holed_face(
            triangles,
            rim_indices[rim_position],
            rims[rim_position],
            tuple(box[key] for key in keys),
            tuple(_corner_point(key, bounds) for key in keys),
            primary,
            flip=not positive,
        )
        opened.add((primary, positive))

    if not through:
        _add_hole_floor(vertices, triangles, rim_indices[1], rims[1])

    for coordinate in range(3):
        for positive in (False, True):
            if (coordinate, positive) in opened:
                continue
            _add_plain_face(triangles, box, coordinate, positive)

    center = tuple(
        (bounds[coordinate][0] + bounds[coordinate][1]) / 2.0 for coordinate in range(3)
    )
    vertices = [
        tuple(point[coordinate] - center[coordinate] for coordinate in range(3))
        for point in vertices
    ]
    return vertices, triangles


def _close_printable_fixture(vertices, triangles, case, basis_u, basis_v, radius, scales):
    sides = SHAPES[case.shape]
    inner_rims = (
        tuple(range(sides)),
        tuple(range(sides, sides * 2)),
    )
    material_margin = 8.0 if case.case_id.startswith("matrix-") else radius * 0.8
    cap_thickness = material_margin if case.case_id.startswith("matrix-") else max(0.5, radius * 0.5)
    outer_axials = (
        -case.depth_mm / 2.0 - (cap_thickness if case.start == "closed" else 0.0),
        case.depth_mm / 2.0 + (cap_thickness if case.end == "closed" else 0.0),
    )
    outer_rims = tuple(
        _add_ring(
            vertices,
            case.axis,
            basis_u,
            basis_v,
            axial,
            radius + material_margin,
            scales,
            case.secondary_radius_scale,
        )
        for axial in outer_axials
    )
    _add_wall(triangles, outer_rims[0], outer_rims[1])

    for level, end in enumerate((case.start, case.end)):
        if end == "open":
            _add_annulus(triangles, inner_rims[level], outer_rims[level])
        else:
            _add_disk(vertices, triangles, inner_rims[level])
            _add_disk(vertices, triangles, outer_rims[level])


def _add_ring(vertices, axis, basis_u, basis_v, axial, radius, scales, secondary_radius_scale):
    rim = []
    for index, scale in enumerate(scales):
        angle = 2.0 * math.pi * index / len(scales)
        rim.append(len(vertices))
        vertices.append(
            tuple(
                axis[coordinate] * axial
                + scale
                * radius
                * (
                    basis_u[coordinate] * math.cos(angle)
                    + secondary_radius_scale * basis_v[coordinate] * math.sin(angle)
                )
                for coordinate in range(3)
            )
        )
    return tuple(rim)


def _add_wall(triangles, first_rim, second_rim):
    for index in range(len(first_rim)):
        following = (index + 1) % len(first_rim)
        triangles.extend(
            (
                (first_rim[index], first_rim[following], second_rim[following]),
                (first_rim[index], second_rim[following], second_rim[index]),
            )
        )


def _add_annulus(triangles, inner_rim, outer_rim):
    for index in range(len(inner_rim)):
        following = (index + 1) % len(inner_rim)
        triangles.extend(
            (
                (inner_rim[index], outer_rim[index], outer_rim[following]),
                (inner_rim[index], outer_rim[following], inner_rim[following]),
            )
        )


def _add_disk(vertices, triangles, rim):
    center = tuple(sum(vertices[index][axis] for index in rim) / len(rim) for axis in range(3))
    center_index = len(vertices)
    vertices.append(center)
    for index in range(len(rim)):
        triangles.append((rim[index], center_index, rim[(index + 1) % len(rim)]))


def _add_end(vertices, triangles, rim, end):
    if end == "broken":
        return
    center = tuple(sum(vertices[index][axis] for index in rim) / len(rim) for axis in range(3))
    if end == "closed":
        center_index = len(vertices)
        vertices.append(center)
        for index in range(len(rim)):
            triangles.append((rim[index], center_index, rim[(index + 1) % len(rim)]))
        return
    outer = []
    for index in rim:
        outer.append(len(vertices))
        vertices.append(tuple(center[axis] + (vertices[index][axis] - center[axis]) * 1.8 for axis in range(3)))
    for index in range(len(rim)):
        following = (index + 1) % len(rim)
        triangles.extend(((rim[index], outer[index], outer[following]), (rim[index], outer[following], rim[following])))


def measured_depth_mm(case: FixtureCase, vertices):
    """穴の壁面を軸方向に測った深さ。

    軸整列の直方体を斜めに貫く穴は端面が斜めに切られるため、公称値より深くなる。
    検出側（cylinder_detection）も壁面頂点の軸方向min/maxを深さとするので、
    ここで実測した値をmanifestの期待値にする。
    """
    if not case.case_id.startswith("matrix-"):
        return case.depth_mm
    wall = vertices[: SHAPES[case.shape] * 2]
    along = [
        sum(point[coordinate] * case.axis[coordinate] for coordinate in range(3))
        for point in wall
    ]
    return round(max(along) - min(along), 9)


def generate(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for case in cases():
        vertices, triangles = build_mesh(case)
        file_name = f"{case.case_id}.stl"
        (output / file_name).write_text(_ascii_stl(case.case_id, vertices, triangles), encoding="ascii")
        manifest.append(
            {
                "id": case.case_id,
                "file": file_name,
                "shape": case.shape,
                "axis": list(case.axis),
                "diameter_mm": case.diameter_mm,
                "depth_mm": measured_depth_mm(case, vertices),
                "end_kind": case.end_kind,
                "expected": case.expected,
                "reason": case.reason,
                "config": dict(case.config),
                "dimension_tolerance_mm": case.dimension_tolerance_mm,
                "printable": case.printable,
                "topology": "closed_two_manifold" if case.printable else "intentionally_non_manifold",
            }
        )
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ascii_stl(name, vertices, triangles):
    lines = [f"solid {name}"]
    for triangle in triangles:
        points = tuple(vertices[index] for index in triangle)
        normal = _normal(*points)
        lines.append(f"  facet normal {_numbers(normal)}")
        lines.append("    outer loop")
        lines.extend(f"      vertex {_numbers(point)}" for point in points)
        lines.extend(("    endloop", "  endfacet"))
    lines.append(f"endsolid {name}")
    return "\n".join(lines) + "\n"


def _numbers(values):
    """往復精度で書き出す。

    桁を落として環境差を吸収する案は採れない。検出の許容差が1e-9のため、それを
    下回る量子で丸める必要がある一方、環境差は1e-15程度あり、丸め境界をまたぐ値
    が確率的に生じる。両立する桁数が存在しないため、精度は保ったままにして、
    committed fixtureとの一致は数値比較で確かめる（tests/test_fixture_suite.py）。
    """
    return " ".join(format(value, ".17g") for value in values)


def _normal(a, b, c):
    normal = _cross(tuple(b[i] - a[i] for i in range(3)), tuple(c[i] - a[i] for i in range(3)))
    length = math.sqrt(sum(value * value for value in normal))
    return (0.0, 0.0, 0.0) if length == 0.0 else tuple(value / length for value in normal)


def _normalize(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return tuple(value / length for value in vector)


def _cross(first, second):
    return (first[1] * second[2] - first[2] * second[1], first[2] * second[0] - first[0] * second[2], first[0] * second[1] - first[1] * second[0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    generate(args.output)
    print(f"{len(cases())} fixtures: {args.output}")


if __name__ == "__main__":
    main()
