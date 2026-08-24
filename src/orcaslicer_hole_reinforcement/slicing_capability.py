"""OrcaSlicerのスライスパイプラインとの境界。"""

import json
from pathlib import Path
from threading import Lock

import orca

from .analysis import AnalysisCancelled, HoleAnalysisCache
from .config import ConfigValidation, default_config_dict
from .config_migration import (
    PRESET_OVERRIDE_KEYS,
    REASON_MIGRATED,
    REASON_UNREADABLE,
    current_plugin_key,
    find_stale_preset_overrides,
    host_config_is_empty,
    migrate_config,
    parse_host_config,
)
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
        self._host_config_path_override = None
        self._migration = None
        self._stale_reported = False
        # execute()はスライスワーカースレッドで走るため、引き継ぎ結果の解決を排他する。
        self._migration_lock = Lock()

    def get_name(self):
        return "Hole Reinforcement"

    def get_default_config(self):
        return default_config_dict()

    def has_config_ui(self):
        return True

    def on_load(self):
        """ホストが既定値を初期投入する直前に、旧バージョンの設定を引き継ぐ。

        ホストは`plugin_loader::load()`の直後、`has_config()`が偽のときだけ
        `get_default_config()`を保存する（`PluginManager.cpp`）。エントリが存在しない
        このタイミングだけが引き継ぎ元を適用できる唯一の機会であり、ここで保存すれば
        ホスト側の初期投入はスキップされる。
        """
        try:
            self._migrate_on_load()
        except Exception:
            # on_load()が例外を送出するとプラグインの読み込み自体が失敗する。
            return

    def _migrate_on_load(self):
        if not host_config_is_empty(self._host_config()):
            return
        migration = self._resolve_migration()
        if migration.reason != REASON_MIGRATED:
            self._report_migration(migration, stored=False)
            return
        stored = self._store_config(migration.config)
        self._report_migration(migration, stored=stored)

    def _store_config(self, config):
        try:
            return bool(
                self.save_config(json.dumps(config.to_dict(), ensure_ascii=False))
            )
        except (AttributeError, RuntimeError):
            return False

    def get_config_ui(self):
        try:
            language = orca.host.app_language()
        except (AttributeError, RuntimeError):
            language = ""
        initial = None
        if host_config_is_empty(self._host_config()):
            initial = self._resolve_migration().config.to_dict()
        return render_config_ui(language, initial, self._stale_preset_overrides())

    def execute(self, ctx):
        if ctx.step not in (
            orca.slicing.Step.posSlice,
            orca.slicing.Step.posPrepareInfill,
        ):
            return orca.ExecutionResult.skipped()

        validation = self._resolve_config()
        if not validation.is_valid:
            return orca.ExecutionResult.failure(
                orca.PluginResult.FatalError,
                f"Hole Reinforcement: invalid configuration: {validation.summary()}",
            )

        if getattr(ctx, "object", None) is None:
            return orca.ExecutionResult.skipped()

        config = validation.config
        assert config is not None
        self._report_stale_overrides()
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

    def _report_stale_overrides(self):
        """スライスのたびではなく、セッション中1回だけ知らせる。"""
        with self._migration_lock:
            if self._stale_reported:
                return
            self._stale_reported = True
        stale = self._stale_preset_overrides()
        if not stale:
            return
        self._migration_sink().emit(
            DiagnosticEvent(
                DiagnosticLevel.WARNING,
                "preset_override_stale",
                "プリセットに旧バージョン向けの設定が残っており、参照されていません",
                {"plugin_keys": list(stale)},
            )
        )

    def _stale_preset_overrides(self):
        """プリセットに残った旧バージョン向けoverrideの`plugin_key`を集める。

        overrideは`plugin_key`込みで保持されるため更新で参照されなくなるが、
        ホストが公開するプリセットAPIは読み取り専用で書き戻して復元できない。
        利用者が黙って失うことのないよう、検知して知らせるだけに留める。

        capability参照（`plugins`）が古い場合はホスト側の`PluginResolver`が通知を出し、
        スライスもブロックするため、こちらでは扱わない。
        """
        scan = {"own_plugin_key": None, "preset_count": 0, "values": {}}
        try:
            own_key = current_plugin_key(Path(__file__).resolve().parent)
            scan["own_plugin_key"] = own_key
            overrides = []
            presets = self._edited_presets()
            scan["preset_count"] = len(presets)
            for preset in presets:
                for key in PRESET_OVERRIDE_KEYS:
                    raw = self._preset_value(preset, key)
                    scan["values"][key] = _describe_preset_value(raw)
                    for plugin_key in find_stale_preset_overrides(
                        raw, self.get_name(), own_key
                    ):
                        if plugin_key not in overrides:
                            overrides.append(plugin_key)
            stale = tuple(overrides)
        except Exception as error:
            scan["error"] = f"{type(error).__name__}: {error}"
            stale = ()
        self._report_preset_scan(scan, stale)
        return stale

    def _report_preset_scan(self, scan, stale):
        """検知が空振りした理由を追えるよう、読み取った内容をそのまま残す。

        握り潰した例外や、想定と違う戻り値の形は、記録しないと実機で追えない。
        """
        self._migration_sink().emit(
            DiagnosticEvent(
                DiagnosticLevel.INFO,
                "preset_scan_completed",
                "プリセットの参照を確認しました",
                {**scan, "stale_overrides": list(stale)},
            )
        )

    @staticmethod
    def _preset_value(preset, key):
        try:
            return preset.config_value(key)
        except Exception:
            return None

    def _edited_presets(self):
        bundle = orca.host.preset_bundle()
        presets = []
        for accessor in ("current_process_preset", "current_print_preset"):
            method = getattr(bundle, accessor, None)
            if method is None:
                continue
            try:
                preset = method()
            except Exception:
                continue
            if preset is not None and preset not in presets:
                presets.append(preset)
        return presets

    def _resolve_config(self):
        # execute()はオブジェクトとステップごとに呼ばれる。空判定と検証で二度パースしない。
        validation = parse_host_config(self._host_config())
        if validation is not None:
            return validation
        # 保存にも初期投入にも失敗したホストでは、引き継ぎ結果か既定値で動く。
        return ConfigValidation(self._resolve_migration().config)

    def _host_config(self):
        """設定を取れないホストでは未保存として扱い、引き継ぎか既定値へ退避する。"""
        try:
            return self.get_config()
        except (AttributeError, RuntimeError):
            return None

    def _resolve_migration(self):
        with self._migration_lock:
            if self._migration is None:
                self._migration = migrate_config(
                    Path(__file__).resolve().parent,
                    self.get_name(),
                    config_path=self._host_config_path_override,
                )
            return self._migration

    def _report_migration(self, migration, *, stored):
        if migration.reason == REASON_MIGRATED:
            event = DiagnosticEvent(
                DiagnosticLevel.INFO,
                "config_migrated",
                "旧バージョンの設定を引き継ぎました",
                {
                    "source_plugin_key": migration.source_plugin_key,
                    "source_plugin_version": migration.source_plugin_version,
                    "rejected_count": migration.rejected_count,
                    "stored": stored,
                },
            )
        elif migration.reason == REASON_UNREADABLE:
            event = DiagnosticEvent(
                DiagnosticLevel.WARNING,
                "config_migration_failed",
                "ホストの設定ファイルを読めなかったため既定値で動作します",
                {"reason": migration.reason},
            )
        else:
            event = DiagnosticEvent(
                DiagnosticLevel.INFO,
                "config_migration_skipped",
                "引き継ぎ元が見つからなかったため既定値で動作します",
                {
                    "reason": migration.reason,
                    "rejected_count": migration.rejected_count,
                },
            )
        self._migration_sink().emit(event)

    def _migration_sink(self):
        """移行の記録はdiagnostics_enabledに依らず残す。

        引き継いだ設定で診断が無効だと、診断を有効化するために設定を保存した時点で
        引き継ぎが発火しなくなり、原因を追う手掛かりが残らないため。
        """
        return self._versioned_sink()

    def _diagnostics(self, config):
        if not config.diagnostics_enabled:
            return NullDiagnosticSink()
        return self._versioned_sink()

    def _versioned_sink(self):
        """全レコードへ実バージョンを載せる。

        wheelメタデータのバージョンは固定値で、ホストが`config.json`へ書く
        `plugin_version`も固定値になる。実バージョンを実機で確認できる経路が
        診断と実行結果メッセージしかないため。
        """
        if self._diagnostic_sink_override is not None:
            target = self._diagnostic_sink_override
        else:
            target = JsonLinesDiagnosticSink(self._diagnostic_path())
        return SafeDiagnosticSink(
            ContextDiagnosticSink(target, {"plugin_version": __version__})
        )

    def _diagnostic_path(self):
        return Path(__file__).resolve().with_name("diagnostic.jsonl")


def _describe_preset_value(raw):
    """値そのものではなく、型と長さと先頭だけを残す。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"type": "str", "length": len(raw), "head": raw[:120]}
    return {"type": type(raw).__name__, "repr": repr(raw)[:120]}


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
