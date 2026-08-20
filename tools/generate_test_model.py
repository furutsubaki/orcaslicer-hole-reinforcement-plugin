"""PROTOTYPE:3種類の垂直円穴を持つASCII STLを生成する。"""

import math
from pathlib import Path


SEGMENTS = 96
HEIGHT_MM = 12.0
OUTER_RADIUS_MM = 8.0
HOLES = [
    (-20.0, 2.0),
    (0.0, 4.5),
    (20.0, 7.0),
]


def _normal(a, b, c):
    ux, uy, uz = (b[index] - a[index] for index in range(3))
    vx, vy, vz = (c[index] - a[index] for index in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if length == 0.0 else (nx / length, ny / length, nz / length)


def _facet(vertices):
    normal = _normal(*vertices)
    lines = [f"  facet normal {normal[0]:.8g} {normal[1]:.8g} {normal[2]:.8g}", "    outer loop"]
    lines.extend(f"      vertex {x:.8g} {y:.8g} {z:.8g}" for x, y, z in vertices)
    lines.extend(["    endloop", "  endfacet"])
    return "\n".join(lines)


def _annulus(center_x, inner_radius):
    facets = []
    for index in range(SEGMENTS):
        angle1 = 2.0 * math.pi * index / SEGMENTS
        angle2 = 2.0 * math.pi * (index + 1) / SEGMENTS
        outer1 = (center_x + OUTER_RADIUS_MM * math.cos(angle1), OUTER_RADIUS_MM * math.sin(angle1))
        outer2 = (center_x + OUTER_RADIUS_MM * math.cos(angle2), OUTER_RADIUS_MM * math.sin(angle2))
        inner1 = (center_x + inner_radius * math.cos(angle1), inner_radius * math.sin(angle1))
        inner2 = (center_x + inner_radius * math.cos(angle2), inner_radius * math.sin(angle2))
        ob1, ob2 = (*outer1, 0.0), (*outer2, 0.0)
        ot1, ot2 = (*outer1, HEIGHT_MM), (*outer2, HEIGHT_MM)
        ib1, ib2 = (*inner1, 0.0), (*inner2, 0.0)
        it1, it2 = (*inner1, HEIGHT_MM), (*inner2, HEIGHT_MM)
        facets.extend([
            (ot1, ot2, it2), (ot1, it2, it1),
            (ob1, ib2, ob2), (ob1, ib1, ib2),
            (ob1, ob2, ot2), (ob1, ot2, ot1),
            (ib1, it2, ib2), (ib1, it1, it2),
        ])
    return facets


def main():
    output = Path(__file__).resolve().parents[1] / "test-models" / "vertical-hole-test.stl"
    output.parent.mkdir(parents=True, exist_ok=True)
    facets = [facet for center_x, inner_radius in HOLES for facet in _annulus(center_x, inner_radius)]
    body = "\n".join(_facet(facet) for facet in facets)
    output.write_text(f"solid vertical_hole_test\n{body}\nendsolid vertical_hole_test\n", encoding="ascii")
    print(output)


if __name__ == "__main__":
    main()
