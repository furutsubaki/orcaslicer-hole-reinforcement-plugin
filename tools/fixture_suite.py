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
        FixtureCase("diameter-below-min", "circle", 90.0, 0.49, 12.0, "open", "open", "not_detected"),
        FixtureCase("diameter-at-min", "circle", 90.0, 0.5, 12.0, "open", "open"),
        FixtureCase("diameter-at-max", "circle", 90.0, 10.0, 12.0, "open", "open"),
        FixtureCase("diameter-above-max", "circle", 90.0, 10.01, 12.0, "open", "open", "not_detected"),
        FixtureCase("depth-below-min", "circle", 90.0, 4.0, 0.99, "open", "open", "not_detected"),
        FixtureCase("depth-at-min", "circle", 90.0, 4.0, 1.0, "open", "open"),
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
        for level, end in ((0, case.start), (1, case.end)):
            _add_end(vertices, triangles, tuple(level * sides + i for i in range(sides)), end)
    return tuple(vertices), tuple(triangles)


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
                "depth_mm": case.depth_mm,
                "end_kind": case.end_kind,
                "expected": case.expected,
                "reason": case.reason,
                "config": dict(case.config),
                "dimension_tolerance_mm": case.dimension_tolerance_mm,
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
