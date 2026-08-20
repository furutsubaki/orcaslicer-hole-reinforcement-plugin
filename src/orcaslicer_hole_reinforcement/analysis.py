"""穴解析の計測と、配置だけが異なる同一形状の再利用を管理する。"""

import hashlib
import struct
import time
import tracemalloc
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace

from .candidate_detection import HoleCandidateDetector
from .config import HoleReinforcementConfig
from .detection import (
    CylindricalHoleCandidate,
    MeshSnapshot,
    PolygonalHoleCandidate,
    Vector3,
)
from .end_classification import (
    ClassifiedHole,
    HoleEndClassifier,
    emit_classification_diagnostic,
)


class AnalysisCancelled(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AnalysisMeasurement:
    duration_seconds: float
    peak_memory_bytes: int
    vertex_count: int
    triangle_count: int
    cache_hit: bool


@dataclass(frozen=True, slots=True)
class _CacheKey:
    shape_digest: bytes
    config: HoleReinforcementConfig


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    anchor: Vector3
    classified: tuple[ClassifiedHole, ...]
    mesh_items: int


class HoleAnalysisCache:
    """メッシュ要素数で上限を設けたLRUキャッシュ。"""

    def __init__(self, *, max_entries: int = 32, max_mesh_items: int = 2_000_000):
        if max_entries < 1 or max_mesh_items < 1:
            raise ValueError("cache limits must be positive")
        self._max_entries = max_entries
        self._max_mesh_items = max_mesh_items
        self._mesh_items = 0
        self._entries: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()

    def analyze(
        self,
        mesh: MeshSnapshot,
        config: HoleReinforcementConfig,
        *,
        diagnostics,
        measure_memory: bool = False,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> tuple[tuple[ClassifiedHole, ...], AnalysisMeasurement]:
        started = time.perf_counter()
        tracing = tracemalloc.is_tracing()
        if measure_memory and not tracing:
            tracemalloc.start()
        memory_before = tracemalloc.get_traced_memory()[0] if measure_memory else 0
        try:
            key, anchor = _cache_key(mesh, config, cancelled)
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                classified = _translate_classified(
                    cached.classified,
                    _subtract(anchor, cached.anchor),
                    cancelled,
                )
                for result in classified:
                    emit_classification_diagnostic(result, config, diagnostics)
                cache_hit = True
            else:
                candidates = HoleCandidateDetector().detect(
                    mesh, config, cancelled=cancelled
                )
                classified = HoleEndClassifier().classify(
                    mesh,
                    candidates,
                    config,
                    diagnostics=diagnostics,
                    cancelled=cancelled,
                )
                self._store(
                    key,
                    _CacheEntry(
                        anchor,
                        classified,
                        len(mesh.vertices_mm) + len(mesh.triangles),
                    ),
                )
                cache_hit = False
            if measure_memory:
                current_after, traced_peak = tracemalloc.get_traced_memory()
                peak = traced_peak if not tracing else max(memory_before, current_after)
            else:
                peak = 0
        finally:
            if measure_memory and not tracing:
                tracemalloc.stop()
        return classified, AnalysisMeasurement(
            duration_seconds=time.perf_counter() - started,
            peak_memory_bytes=max(0, peak - memory_before),
            vertex_count=len(mesh.vertices_mm),
            triangle_count=len(mesh.triangles),
            cache_hit=cache_hit,
        )

    def clear(self) -> None:
        self._entries.clear()
        self._mesh_items = 0

    def _store(self, key: _CacheKey, entry: _CacheEntry) -> None:
        if entry.mesh_items > self._max_mesh_items:
            return
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._mesh_items -= previous.mesh_items
        self._entries[key] = entry
        self._mesh_items += entry.mesh_items
        while (
            len(self._entries) > self._max_entries
            or self._mesh_items > self._max_mesh_items
        ):
            _, removed = self._entries.popitem(last=False)
            self._mesh_items -= removed.mesh_items


def _cache_key(
    mesh: MeshSnapshot,
    config: HoleReinforcementConfig,
    cancelled: Callable[[], bool],
) -> tuple[_CacheKey, Vector3]:
    anchor = mesh.vertices_mm[0] if mesh.vertices_mm else (0.0, 0.0, 0.0)
    digest = hashlib.blake2b(digest_size=20)
    digest.update(struct.pack("!QQ", len(mesh.vertices_mm), len(mesh.triangles)))
    for index, vertex in enumerate(mesh.vertices_mm):
        if index % 4096 == 0 and cancelled():
            raise AnalysisCancelled
        digest.update(struct.pack("!ddd", *(_subtract(vertex, anchor))))
    for index, triangle in enumerate(mesh.triangles):
        if index % 4096 == 0 and cancelled():
            raise AnalysisCancelled
        digest.update(struct.pack("!QQQ", *triangle))
    return _CacheKey(digest.digest(), config), anchor


def _translate_classified(
    classified: tuple[ClassifiedHole, ...],
    delta: Vector3,
    cancelled: Callable[[], bool],
) -> tuple[ClassifiedHole, ...]:
    if delta == (0.0, 0.0, 0.0):
        return classified
    translated = []
    for index, item in enumerate(classified):
        if index % 256 == 0 and cancelled():
            raise AnalysisCancelled
        translated.append(
            replace(item, candidate=_translate_candidate(item.candidate, delta))
        )
    return tuple(translated)


def _translate_candidate(candidate, delta: Vector3):
    axial_delta = sum(delta[index] * candidate.axis[index] for index in range(3))
    values = {
        "center_mm": _add(candidate.center_mm, delta),
        "axial_start_mm": candidate.axial_start_mm + axial_delta,
        "axial_end_mm": candidate.axial_end_mm + axial_delta,
    }
    if isinstance(candidate, PolygonalHoleCandidate):
        values["cross_section_mm"] = tuple(
            _add(point, delta) for point in candidate.cross_section_mm
        )
    if not isinstance(candidate, (CylindricalHoleCandidate, PolygonalHoleCandidate)):
        raise TypeError("unsupported hole candidate")
    return replace(candidate, **values)


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(left[index] + right[index] for index in range(3))  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(left[index] - right[index] for index in range(3))  # type: ignore[return-value]
