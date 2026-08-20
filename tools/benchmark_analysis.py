"""代表的なメッシュ規模で穴解析の時間、ピークメモリ、再利用結果を計測する。"""

import argparse
import math
from dataclasses import asdict
import json

from orcaslicer_hole_reinforcement.analysis import HoleAnalysisCache
from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.detection import MeshSnapshot
from orcaslicer_hole_reinforcement.diagnostics import NullDiagnosticSink


def cylinder_wall(segments: int, levels: int, *, offset: float = 0.0) -> MeshSnapshot:
    vertices = tuple(
        (
            offset + 2.0 * math.cos(2.0 * math.pi * segment / segments),
            2.0 * math.sin(2.0 * math.pi * segment / segments),
            8.0 * level / levels,
        )
        for level in range(levels + 1)
        for segment in range(segments)
    )
    triangles = []
    for level in range(levels):
        for segment in range(segments):
            following = (segment + 1) % segments
            lower = level * segments
            upper = (level + 1) * segments
            triangles.extend(
                (
                    (lower + segment, upper + following, upper + segment),
                    (lower + segment, lower + following, upper + following),
                )
            )
    return MeshSnapshot(vertices, tuple(triangles))


def benchmark(segments: int, levels: int) -> dict[str, object]:
    config = HoleReinforcementConfig(enabled_shapes=("circle",))
    source = cylinder_wall(segments, levels)
    translated = cylinder_wall(segments, levels, offset=25.0)
    measured_cache = HoleAnalysisCache(max_mesh_items=10_000_000)
    _, memory = measured_cache.analyze(
        source,
        config,
        diagnostics=NullDiagnosticSink(),
        measure_memory=True,
    )
    cache = HoleAnalysisCache(max_mesh_items=10_000_000)
    first, cold = cache.analyze(
        source, config, diagnostics=NullDiagnosticSink()
    )
    second, warm = cache.analyze(
        translated, config, diagnostics=NullDiagnosticSink()
    )
    direct, _ = HoleAnalysisCache(max_mesh_items=10_000_000).analyze(
        translated, config, diagnostics=NullDiagnosticSink()
    )
    if second != direct:
        raise RuntimeError("cached analysis differs from uncached analysis")
    return {
        "segments": segments,
        "levels": levels,
        "cold": {**asdict(cold), "peak_memory_bytes": memory.peak_memory_bytes},
        "warm": asdict(warm),
        "detected_count": len(first),
        "equivalent": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    results = [benchmark(*size) for size in ((48, 10), (96, 50), (192, 100))]
    if arguments.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print("|規模|頂点|三角形|初回時間|再利用時間|初回ピークメモリ|結果一致|")
    print("|---:|---:|---:|---:|---:|---:|:---:|")
    for result in results:
        cold = result["cold"]
        warm = result["warm"]
        print(
            f"|{result['segments']}×{result['levels']}"
            f"|{cold['vertex_count']}|{cold['triangle_count']}"
            f"|{cold['duration_seconds']:.6f}秒"
            f"|{warm['duration_seconds']:.6f}秒"
            f"|{cold['peak_memory_bytes']}B|✓|"
        )


if __name__ == "__main__":
    main()
