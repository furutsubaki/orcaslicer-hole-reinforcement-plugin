"""生成済みSTLをOrcaSlicerなしで検出・穴端分類する。"""

import argparse
import json
import math
from pathlib import Path

from orcaslicer_hole_reinforcement.candidate_detection import HoleCandidateDetector
from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.detection import MeshSnapshot
from orcaslicer_hole_reinforcement.end_classification import HoleEndClassifier


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "test-models" / "fixtures"


def load_ascii_stl(path: Path) -> MeshSnapshot:
    vertices = []
    indices = {}
    triangles = []
    pending = []
    for line in path.read_text(encoding="ascii").splitlines():
        fields = line.split()
        if not fields or fields[0] != "vertex":
            continue
        vertex = tuple(float(value) for value in fields[1:4])
        index = indices.get(vertex)
        if index is None:
            index = len(vertices)
            indices[vertex] = index
            vertices.append(vertex)
        pending.append(index)
        if len(pending) == 3:
            triangles.append(tuple(pending))
            pending.clear()
    if pending or not triangles:
        raise ValueError(f"invalid ASCII STL: {path}")
    return MeshSnapshot(tuple(vertices), tuple(triangles))


def verify(directory: Path) -> list[str]:
    failures = []
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest:
        config = HoleReinforcementConfig(
            enabled_shapes=(case["shape"],), **case.get("config", {})
        )
        mesh = load_ascii_stl(_fixture_path(directory, case["file"]))
        candidates = HoleCandidateDetector().detect(mesh, config)
        classified = HoleEndClassifier().classify(mesh, candidates, config)
        accepted = tuple(item for item in classified if item.accepted)
        if case["expected"] == "not_detected":
            if candidates:
                failures.append(f"{case['id']}: expected no candidate, got {len(candidates)}")
            continue
        if case["expected"] == "rejected":
            if len(classified) != 1 or classified[0].accepted or classified[0].reason != case["reason"]:
                failures.append(f"{case['id']}: expected rejection {case['reason']}")
            continue
        if len(accepted) != 1:
            failures.append(f"{case['id']}: expected one accepted hole, got {len(accepted)}")
            continue
        hole = accepted[0]
        actual_shape = "circle" if hasattr(hole.candidate, "radius_mm") else hole.candidate.shape.value
        diameter = hole.candidate.radius_mm * 2.0 if hasattr(hole.candidate, "radius_mm") else hole.candidate.across_flats_mm
        axis_dot = abs(sum(left * right for left, right in zip(hole.candidate.axis, case["axis"])))
        if actual_shape != case["shape"]:
            failures.append(f"{case['id']}: shape {actual_shape} != {case['shape']}")
        if hole.end_kind is None or hole.end_kind.value != case["end_kind"]:
            failures.append(f"{case['id']}: end kind mismatch")
        dimension_tolerance = case.get("dimension_tolerance_mm", 1e-6)
        if not math.isclose(diameter, case["diameter_mm"], abs_tol=dimension_tolerance):
            failures.append(f"{case['id']}: diameter {diameter:g} != {case['diameter_mm']:g}")
        if not math.isclose(hole.candidate.depth_mm, case["depth_mm"], abs_tol=dimension_tolerance):
            failures.append(f"{case['id']}: depth mismatch")
        if not math.isclose(axis_dot, 1.0, abs_tol=1e-6):
            failures.append(f"{case['id']}: axis mismatch")
    return failures


def _fixture_path(directory: Path, file_name: str) -> Path:
    if Path(file_name).name != file_name:
        raise ValueError(f"fixture file must be a basename: {file_name}")
    return directory / file_name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    failures = verify(args.fixtures)
    if failures:
        raise SystemExit("\n".join(failures))
    count = len(json.loads((args.fixtures / "manifest.json").read_text(encoding="utf-8")))
    print(f"{count} fixtures passed")


if __name__ == "__main__":
    main()
