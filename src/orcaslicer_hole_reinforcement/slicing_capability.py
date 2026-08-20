"""OrcaSlicerのスライスパイプラインとの境界。"""

from pathlib import Path

import orca

from .analysis import AnalysisCancelled, HoleAnalysisCache
from .config import default_config_dict, parse_json_config
from .config_ui import render_config_ui
from .cylinder_detection import CylinderDetectionCancelled
from .end_classification import HoleEndClassificationCancelled
from .diagnostics import (
    ContextDiagnosticSink,
    DiagnosticEvent,
    DiagnosticLevel,
    JsonLinesDiagnosticSink,
    NullDiagnosticSink,
    SafeDiagnosticSink,
)
from .mesh_extraction import (
    MeshExtractionCancelled,
    VolumeRole,
    extract_transformed_volumes,
)
from .orca_geometry import OrcaPlanarGeometry
from .polygon_detection import PolygonDetectionCancelled
from .reinforcement import (
    LayerHoleContour,
    LayerPlane,
    ReinforcementPlanningCancelled,
    ReinforcementVolumeSlicer,
)
from .solid_reinforcement import SolidReinforcementCancelled, apply_solid_reinforcement
from .version import __version__


class HoleReinforcementCapability(orca.slicing.SlicingPipelineCapabilityBase):
    def __init__(self):
        super().__init__()
        self._classified_by_object = {}
        self._diagnostic_sink_override = None
        self._analysis_cache = HoleAnalysisCache()

    def get_name(self):
        return "Hole Reinforcement"

    def get_default_config(self):
        return default_config_dict()

    def has_config_ui(self):
        return True

    def get_config_ui(self):
        try:
            language = orca.host.app_language()
        except (AttributeError, RuntimeError):
            language = ""
        return render_config_ui(language)

    def execute(self, ctx):
        if ctx.step not in (
            orca.slicing.Step.posSlice,
            orca.slicing.Step.posPrepareInfill,
        ):
            return orca.ExecutionResult.skipped()

        validation = parse_json_config(self.get_config())
        if not validation.is_valid:
            return orca.ExecutionResult.failure(
                orca.PluginResult.FatalError,
                f"Hole Reinforcement: invalid configuration: {validation.summary()}",
            )

        if getattr(ctx, "object", None) is None:
            return orca.ExecutionResult.skipped()

        config = validation.config
        assert config is not None
        try:
            if ctx.step == orca.slicing.Step.posSlice:
                return self._detect(ctx, config)
            return self._reinforce(ctx, config)
        except (
            MeshExtractionCancelled,
            CylinderDetectionCancelled,
            PolygonDetectionCancelled,
            HoleEndClassificationCancelled,
            ReinforcementPlanningCancelled,
            SolidReinforcementCancelled,
            AnalysisCancelled,
        ):
            return orca.ExecutionResult.success("Hole Reinforcement: cancelled")

    def _detect(self, ctx, config):
        object_id = int(ctx.object.id())
        self._classified_by_object.pop(object_id, None)
        diagnostics = ContextDiagnosticSink(
            self._diagnostics(config), _object_context(ctx)
        )
        classified = []
        excluded_volumes = []
        volumes = extract_transformed_volumes(
            ctx.object,
            include_roles=frozenset((VolumeRole.MODEL_PART,)),
            on_excluded=lambda volume_id, volume_index, role: excluded_volumes.append(
                (volume_id, volume_index, role)
            ),
            cancelled=ctx.cancelled,
        )
        for volume_id, volume_index, role in excluded_volumes:
            ContextDiagnosticSink(
                diagnostics,
                {
                    "volume_id": volume_id,
                    "volume_index": volume_index,
                    "volume_role": role.value,
                },
            ).emit(
                DiagnosticEvent(
                    DiagnosticLevel.INFO,
                    "volume_detection_skipped",
                    "検出対象外のボリュームを除外しました",
                    {"reason": "unsupported_volume_role"},
                )
            )
        for volume in volumes:
            if ctx.cancelled():
                return orca.ExecutionResult.success("Hole Reinforcement: cancelled")
            volume_diagnostics = ContextDiagnosticSink(
                diagnostics,
                {
                    "volume_id": volume.volume_id,
                    "volume_index": volume.volume_index,
                    "volume_role": volume.role.value,
                },
            )
            if volume.role is not VolumeRole.MODEL_PART:
                volume_diagnostics.emit(
                    DiagnosticEvent(
                        DiagnosticLevel.INFO,
                        "volume_detection_skipped",
                        "検出対象外のボリュームを除外しました",
                        {"reason": "unsupported_volume_role"},
                    )
                )
                continue
            classified_volume, measurement = self._analysis_cache.analyze(
                volume.mesh,
                config,
                diagnostics=volume_diagnostics,
                cancelled=ctx.cancelled,
            )
            classified.extend(classified_volume)
            volume_diagnostics.emit(
                DiagnosticEvent(
                    DiagnosticLevel.INFO,
                    "volume_detection_completed",
                    "ボリュームの穴検出が完了しました",
                    {
                        "candidate_count": len(classified_volume),
                        "accepted_count": sum(hole.accepted for hole in classified_volume),
                        "excluded_count": sum(
                            not hole.accepted for hole in classified_volume
                        ),
                        "analysis_seconds": measurement.duration_seconds,
                        "vertex_count": measurement.vertex_count,
                        "triangle_count": measurement.triangle_count,
                        "cache_hit": measurement.cache_hit,
                    },
                )
            )
        self._classified_by_object[object_id] = tuple(classified)
        accepted = sum(hole.accepted for hole in classified)
        diagnostics.emit(
            DiagnosticEvent(
                DiagnosticLevel.INFO,
                "object_detection_completed",
                "オブジェクトの穴検出が完了しました",
                {
                    "volume_count": len(volumes),
                    "candidate_count": len(classified),
                    "accepted_count": accepted,
                    "excluded_count": len(classified) - accepted,
                },
            )
        )
        return orca.ExecutionResult.success(
            f"Hole Reinforcement {__version__}: detected {accepted} hole(s)"
        )

    def _reinforce(self, ctx, config):
        if not config.solid_reinforcement:
            return orca.ExecutionResult.skipped("Hole Reinforcement: disabled")
        holes = self._classified_by_object.get(int(ctx.object.id()), ())
        if not any(hole.accepted for hole in holes):
            return orca.ExecutionResult.skipped("Hole Reinforcement: no target holes")

        geometry = OrcaPlanarGeometry()
        host_layers = list(ctx.object.layers())
        layers = []
        for index, layer in enumerate(host_layers):
            if ctx.cancelled():
                return orca.ExecutionResult.success("Hole Reinforcement: cancelled")
            layers.append(_copy_layer_plane(index, layer, holes, geometry, ctx.cancelled))
        planned = ReinforcementVolumeSlicer(geometry).plan(
            holes,
            tuple(layers),
            config,
            cancelled=ctx.cancelled,
        )
        result = apply_solid_reinforcement(
            host_layers,
            planned,
            geometry,
            cancelled=ctx.cancelled,
        )
        details = {
            "reinforced_layer_count": len(planned),
            "target_region_count": sum(len(region.regions) for region in planned),
            "solid_surface_count": result.solid_surfaces,
            "changed_collection_count": result.changed_collections,
        }
        # 明細はレイヤ数に比例するため、診断を切っているときは組み立てない。
        if config.diagnostics_enabled:
            details["reinforced_layers"] = _reinforced_layer_details(planned, layers)
        diagnostics = ContextDiagnosticSink(
            self._diagnostics(config), _object_context(ctx)
        )
        diagnostics.emit(
            DiagnosticEvent(
                DiagnosticLevel.INFO,
                "reinforcement_completed",
                "ソリッド補強が完了しました",
                details,
            )
        )
        return orca.ExecutionResult.success(
            "Hole Reinforcement: solidified "
            f"{result.solid_surfaces} surface(s) in "
            f"{result.changed_collections} collection(s)"
        )

    def _diagnostics(self, config):
        if not config.diagnostics_enabled:
            return NullDiagnosticSink()
        if self._diagnostic_sink_override is not None:
            return SafeDiagnosticSink(self._diagnostic_sink_override)
        path = Path(__file__).resolve().with_name("diagnostic.jsonl")
        return SafeDiagnosticSink(JsonLinesDiagnosticSink(path))


def _object_context(ctx):
    model_object = ctx.object.model_object()
    context = {
        "print_object_id": int(ctx.object.id()),
        "model_object_id": int(model_object.id()),
    }
    name = _model_object_name(model_object)
    if name is not None:
        context["model_object_name"] = name
    else:
        # 名前を辿れないホストでは、取得先を特定できるよう手掛かりを残す。
        context["model_object_attributes"] = _public_attributes(model_object)
    # model_object_idは実行時IDで3mfのidとは別体系のため、配置を対応付けの拠り所にする。
    origin = _object_origin(ctx.object)
    if origin is not None:
        context["object_origin_mm"] = origin
    return context


def _model_object_name(model_object):
    """ホストが名前をメソッドで返すか属性で持つかは環境差があるため両方試す。"""
    for attribute in ("name", "get_name", "object_name"):
        value = getattr(model_object, attribute, None)
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, str) and value:
            return value
    return None


def _public_attributes(value):
    try:
        names = sorted(name for name in dir(value) if not name.startswith("_"))
    except Exception:
        return ()
    return tuple(names[:40])


def _object_origin(print_object):
    try:
        matrix = print_object.trafo()
        return tuple(round(float(matrix[row][3]), 6) for row in range(3))
    except Exception:
        return None


def _reinforced_layer_details(planned, layers):
    planes = {plane.index: plane for plane in layers}
    details = []
    for region in planned:
        detail = {
            "layer_index": region.layer_index,
            "region_count": len(region.regions),
        }
        plane = planes.get(region.layer_index)
        if plane is not None:
            detail["print_z_mm"] = plane.print_z_mm
        bbox = _regions_bbox(region.regions)
        if bbox is not None:
            detail["bbox_mm"] = bbox
        details.append(detail)
    return tuple(details)


def _regions_bbox(regions):
    bounds = None
    for region in regions:
        for x, y in region.contour_mm:
            if bounds is None:
                bounds = [x, y, x, y]
                continue
            if x < bounds[0]:
                bounds[0] = x
            if y < bounds[1]:
                bounds[1] = y
            if x > bounds[2]:
                bounds[2] = x
            if y > bounds[3]:
                bounds[3] = y
    return tuple(bounds) if bounds is not None else None


def _copy_layer_plane(index, layer, holes, geometry, cancelled=lambda: False):
    print_z = float(layer.print_z)
    model_regions = geometry.from_host(layer.lslices())
    contours = []
    for region in layer.regions():
        for surface in region.slices.surfaces:
            if cancelled():
                raise ReinforcementPlanningCancelled
            contours.extend(
                geometry.polygon_from_host(hole)
                for hole in surface.expolygon.holes
            )
    matched = _match_hole_contours(holes, contours, print_z)
    return LayerPlane(index, print_z, model_regions, matched)


def _match_hole_contours(holes, contours, print_z):
    available = list(contours)
    matched = []
    for hole_index, hole in enumerate(holes):
        if not hole.accepted:
            continue
        expected = _axis_center_at_z(hole.candidate, print_z)
        if expected is None or not available:
            continue
        contour = min(
            available,
            key=lambda item: _distance_squared(_polygon_centroid(item), expected),
        )
        maximum_distance = _candidate_diameter(hole.candidate)
        if _distance_squared(_polygon_centroid(contour), expected) > maximum_distance**2:
            continue
        matched.append(LayerHoleContour(hole_index, contour))
        available.remove(contour)
    return tuple(matched)


def _axis_center_at_z(candidate, print_z):
    if abs(candidate.axis[2]) <= 1e-9:
        return candidate.center_mm[0], candidate.center_mm[1]
    distance = (print_z - candidate.center_mm[2]) / candidate.axis[2]
    point = tuple(
        candidate.center_mm[index] + candidate.axis[index] * distance
        for index in range(3)
    )
    axial = sum(point[index] * candidate.axis[index] for index in range(3))
    if axial < candidate.axial_start_mm - 1e-7 or axial > candidate.axial_end_mm + 1e-7:
        return None
    return point[0], point[1]


def _candidate_diameter(candidate):
    if hasattr(candidate, "radius_mm"):
        return candidate.radius_mm * 2.0
    return candidate.across_flats_mm


def _polygon_centroid(polygon):
    area_twice = sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(polygon, polygon[1:] + polygon[:1])
    )
    if abs(area_twice) <= 1e-12:
        return polygon[0]
    return tuple(
        sum(
            (first[axis] + second[axis])
            * (first[0] * second[1] - second[0] * first[1])
            for first, second in zip(polygon, polygon[1:] + polygon[:1])
        )
        / (3.0 * area_twice)
        for axis in range(2)
    )


def _distance_squared(first, second):
    return sum((a - b) ** 2 for a, b in zip(first, second))
