import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.diagnostics import (
    DiagnosticLevel,
    MemoryDiagnosticSink,
)
from orcaslicer_hole_reinforcement.reinforcement import (
    PlanarRegion,
    ReinforcementRegion,
)


def escape_string_cstyle(text):
    """ホストの`escape_string_cstyle()`（`Config.cpp`）と同じ変換。"""
    out = []
    for character in text:
        if character == "\r":
            out.append("\\r")
        elif character == "\n":
            out.append("\\n")
        elif character in ("\\", '"'):
            out.append("\\" + character)
        else:
            out.append(character)
    return "".join(out)


class Base:
    def __init__(self):
        self.base_initialized = True


def load_module():
    orca = types.ModuleType("orca")
    orca.slicing = types.SimpleNamespace(
        SlicingPipelineCapabilityBase=Base,
        Step=types.SimpleNamespace(posSlice="slice", posPrepareInfill="infill"),
        unscale=lambda value: value / 1000.0,
    )
    orca.host = types.SimpleNamespace(app_language=lambda: "ja_JP")
    orca.ExecutionResult = types.SimpleNamespace(
        success=lambda message="": ("success", message),
        skipped=lambda message="": ("skipped", message),
    )
    sys.modules["orca"] = orca
    for name in (
        "orcaslicer_hole_reinforcement.orca_geometry",
        "orcaslicer_hole_reinforcement.solid_reinforcement",
        "orcaslicer_hole_reinforcement.slicing_capability",
    ):
        sys.modules.pop(name, None)
    return importlib.import_module(
        "orcaslicer_hole_reinforcement.slicing_capability"
    )


class SlicingDiagnosticsTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("orca", None)
        for name in (
            "orcaslicer_hole_reinforcement.orca_geometry",
            "orcaslicer_hole_reinforcement.solid_reinforcement",
            "orcaslicer_hole_reinforcement.slicing_capability",
        ):
            sys.modules.pop(name, None)

    def test_initializes_slicing_pipeline_base(self):
        module = load_module()

        capability = module.HoleReinforcementCapability()

        self.assertTrue(capability.base_initialized)

    def test_every_diagnostic_record_carries_the_real_plugin_version(self):
        from orcaslicer_hole_reinforcement.version import __version__

        module = load_module()
        capability = module.HoleReinforcementCapability()
        diagnostics = MemoryDiagnosticSink()
        capability._diagnostic_sink_override = diagnostics

        sink = capability._diagnostics(HoleReinforcementConfig())
        sink.emit(
            module.DiagnosticEvent(
                module.DiagnosticLevel.INFO, "probe", "probe", {}
            )
        )

        self.assertEqual(diagnostics.events[0].details["plugin_version"], __version__)

    def test_detection_events_identify_model_and_each_volume(self):
        module = load_module()
        capability = module.HoleReinforcementCapability()
        diagnostics = MemoryDiagnosticSink()
        capability._diagnostic_sink_override = diagnostics
        model_object = types.SimpleNamespace(id=lambda: 20)
        print_object = types.SimpleNamespace(
            id=lambda: 10,
            model_object=lambda: model_object,
        )
        ctx = types.SimpleNamespace(object=print_object, cancelled=lambda: False)
        volumes = (
            types.SimpleNamespace(
                model_object_id=20,
                volume_id=30,
                volume_index=0,
                role=module.VolumeRole.MODEL_PART,
                mesh=object(),
            ),
            types.SimpleNamespace(
                model_object_id=20,
                volume_id=31,
                volume_index=1,
                role=module.VolumeRole.NEGATIVE,
                mesh=object(),
            ),
        )
        classified = (types.SimpleNamespace(accepted=True),)
        measurement = types.SimpleNamespace(
            duration_seconds=0.01,
            peak_memory_bytes=1024,
            vertex_count=10,
            triangle_count=20,
            cache_hit=False,
        )
        analyzer = types.SimpleNamespace(
            analyze=lambda *args, **kwargs: (classified, measurement)
        )
        capability._analysis_cache = analyzer

        with patch.object(module, "extract_transformed_volumes", return_value=volumes):
            result = capability._detect(ctx, HoleReinforcementConfig())

        self.assertEqual(result[0], "success")
        by_code = {event.code: event for event in diagnostics.events}
        self.assertEqual(
            by_code["volume_detection_completed"].details["volume_id"], 30
        )
        self.assertEqual(
            by_code["volume_detection_skipped"].details["volume_id"], 31
        )
        self.assertEqual(
            by_code["object_detection_completed"].details["model_object_id"], 20
        )
        self.assertEqual(
            by_code["volume_detection_completed"].details["analysis_seconds"], 0.01
        )

    def test_disabled_diagnostics_does_not_use_override(self):
        module = load_module()
        capability = module.HoleReinforcementCapability()
        diagnostics = MemoryDiagnosticSink()
        capability._diagnostic_sink_override = diagnostics

        sink = capability._diagnostics(
            HoleReinforcementConfig(diagnostics_enabled=False)
        )
        sink.emit(module.DiagnosticEvent(module.DiagnosticLevel.INFO, "test", "test"))

        self.assertEqual(diagnostics.events, [])

    def _detect_with_model_object(self, module, model_object, trafo=None):
        capability = module.HoleReinforcementCapability()
        diagnostics = MemoryDiagnosticSink()
        capability._diagnostic_sink_override = diagnostics
        print_object = types.SimpleNamespace(
            id=lambda: 10,
            model_object=lambda: model_object,
            trafo=lambda: trafo
            or (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
        )
        ctx = types.SimpleNamespace(object=print_object, cancelled=lambda: False)
        capability._analysis_cache = types.SimpleNamespace(
            analyze=lambda *args, **kwargs: ((), types.SimpleNamespace(
                duration_seconds=0.0,
                peak_memory_bytes=0,
                vertex_count=0,
                triangle_count=0,
                cache_hit=False,
            ))
        )

        with patch.object(module, "extract_transformed_volumes", return_value=()):
            capability._detect(ctx, HoleReinforcementConfig())

        return {event.code: event for event in diagnostics.events}

    def test_detection_event_records_model_object_name(self):
        module = load_module()
        model_object = types.SimpleNamespace(
            id=lambda: 20, name=lambda: "matrix-circle-through-0.stl"
        )

        by_code = self._detect_with_model_object(module, model_object)

        self.assertEqual(
            by_code["object_detection_completed"].details["model_object_name"],
            "matrix-circle-through-0.stl",
        )

    def test_detection_event_omits_name_when_host_raises(self):
        module = load_module()

        def raise_error():
            raise RuntimeError("no name")

        model_object = types.SimpleNamespace(id=lambda: 20, name=raise_error)

        by_code = self._detect_with_model_object(module, model_object)

        self.assertNotIn(
            "model_object_name", by_code["object_detection_completed"].details
        )

    def test_detection_event_reads_name_held_as_a_plain_attribute(self):
        module = load_module()
        model_object = types.SimpleNamespace(id=lambda: 20, name="matrix-circle-blind-0.stl")

        by_code = self._detect_with_model_object(module, model_object)

        self.assertEqual(
            by_code["object_detection_completed"].details["model_object_name"],
            "matrix-circle-blind-0.stl",
        )

    def test_detection_event_falls_back_to_alternate_accessor(self):
        module = load_module()
        model_object = types.SimpleNamespace(
            id=lambda: 20, get_name=lambda: "matrix-hexagon-through-45.stl"
        )

        by_code = self._detect_with_model_object(module, model_object)

        self.assertEqual(
            by_code["object_detection_completed"].details["model_object_name"],
            "matrix-hexagon-through-45.stl",
        )

    def test_detection_event_lists_attributes_when_no_name_is_reachable(self):
        module = load_module()
        model_object = types.SimpleNamespace(id=lambda: 20, volume_count=lambda: 1)

        by_code = self._detect_with_model_object(module, model_object)
        details = by_code["object_detection_completed"].details

        self.assertNotIn("model_object_name", details)
        self.assertIn("volume_count", details["model_object_attributes"])

    def test_detection_event_records_object_origin(self):
        module = load_module()
        model_object = types.SimpleNamespace(id=lambda: 20, name=lambda: "a.stl")
        trafo = (
            (1.0, 0.0, 0.0, 175.0),
            (0.0, 1.0, 0.0, 120.5),
            (0.0, 0.0, 1.0, 4.0),
            (0.0, 0.0, 0.0, 1.0),
        )

        by_code = self._detect_with_model_object(module, model_object, trafo=trafo)

        self.assertEqual(
            by_code["object_detection_completed"].details["object_origin_mm"],
            (175.0, 120.5, 4.0),
        )

    def test_detection_event_omits_empty_name(self):
        module = load_module()
        model_object = types.SimpleNamespace(id=lambda: 20, name=lambda: "")

        by_code = self._detect_with_model_object(module, model_object)

        self.assertNotIn(
            "model_object_name", by_code["object_detection_completed"].details
        )

    def test_reinforcement_event_identifies_model_and_target_layers(self):
        module = load_module()
        capability = module.HoleReinforcementCapability()
        diagnostics = MemoryDiagnosticSink()
        capability._diagnostic_sink_override = diagnostics
        model_object = types.SimpleNamespace(
            id=lambda: 20, name=lambda: "matrix-circle-through-0.stl"
        )
        print_object = types.SimpleNamespace(
            id=lambda: 10,
            model_object=lambda: model_object,
            layers=lambda: [object(), object()],
        )
        ctx = types.SimpleNamespace(object=print_object, cancelled=lambda: False)
        capability._classified_by_object[10] = (types.SimpleNamespace(accepted=True),)
        planes = [module.LayerPlane(0, 0.2), module.LayerPlane(1, 0.4)]
        planned = (
            ReinforcementRegion(
                1,
                (PlanarRegion(((0.0, 0.0), (2.0, 0.0), (2.0, 3.0), (0.0, 3.0))),),
            ),
        )
        slicer = types.SimpleNamespace(plan=lambda *args, **kwargs: planned)
        applied = types.SimpleNamespace(solid_surfaces=5, changed_collections=4)

        with (
            patch.object(module, "OrcaPlanarGeometry", return_value=object()),
            patch.object(
                module,
                "_copy_layer_plane",
                side_effect=lambda index, layer, holes, geometry, cancelled: planes[
                    index
                ],
            ),
            patch.object(module, "ReinforcementVolumeSlicer", return_value=slicer),
            patch.object(module, "apply_solid_reinforcement", return_value=applied),
        ):
            result = capability._reinforce(ctx, HoleReinforcementConfig())

        self.assertEqual(result[0], "success")
        event = next(
            item for item in diagnostics.events if item.code == "reinforcement_completed"
        )
        self.assertEqual(
            event.details["model_object_name"], "matrix-circle-through-0.stl"
        )
        self.assertEqual(event.details["print_object_id"], 10)
        self.assertEqual(event.details["model_object_id"], 20)
        self.assertEqual(event.details["reinforced_layer_count"], 1)
        layer_detail = event.details["reinforced_layers"][0]
        self.assertEqual(layer_detail["layer_index"], 1)
        self.assertEqual(layer_detail["print_z_mm"], 0.4)
        self.assertEqual(layer_detail["bbox_mm"], (0.0, 0.0, 2.0, 3.0))


class ConfigMigrationCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config_path = Path(self.temp.name) / "config.json"
        self.diagnostics = MemoryDiagnosticSink()
        self.saved = []

    def tearDown(self):
        sys.modules.pop("orca", None)
        for name in (
            "orcaslicer_hole_reinforcement.orca_geometry",
            "orcaslicer_hole_reinforcement.solid_reinforcement",
            "orcaslicer_hole_reinforcement.slicing_capability",
        ):
            sys.modules.pop(name, None)

    def write_host_config(self, cap_config):
        self.config_path.write_text(
            json.dumps(
                {
                    "config": [
                        {
                            "capability": "Hole Reinforcement",
                            "capability_type": "slicing-pipeline",
                            "plugin_key": "orcaslicer_hole_reinforcement-0.1.0-py3-none-any",
                            "plugin_version": "0.1.0",
                            "cap_config": cap_config,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def build_capability(self, host_config="{}", save_result=True):
        """ホストがまだ既定値を初期投入していない状態のcapabilityを作る。"""
        capability = self.module.HoleReinforcementCapability()
        capability.get_config = lambda: host_config
        capability._host_config_path_override = self.config_path
        capability._diagnostic_sink_override = self.diagnostics

        def save_config(config_str):
            self.saved.append(json.loads(config_str))
            return save_result

        capability.save_config = save_config
        return capability

    def stored_config(self, **overrides):
        return {**HoleReinforcementConfig().to_dict(), **overrides}

    def events(self, code):
        return [event for event in self.diagnostics.events if event.code == code]

    def detect_context(self):
        model_object = types.SimpleNamespace(id=lambda: 20, name="fixture.stl")
        print_object = types.SimpleNamespace(
            id=lambda: 10,
            model_object=lambda: model_object,
        )
        return types.SimpleNamespace(
            step="slice", object=print_object, cancelled=lambda: False
        )

    def run_detect(self, capability, times=1):
        ctx = self.detect_context()
        with patch.object(self.module, "extract_transformed_volumes", return_value=()):
            for _ in range(times):
                capability.execute(ctx)

    def test_on_load_stores_the_migrated_config(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability()

        capability.on_load()

        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0]["reinforcement_width_mm"], 3.5)
        self.assertEqual(set(self.saved[0]), set(HoleReinforcementConfig().to_dict()))
        events = self.events("config_migrated")
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].details["stored"])
        self.assertEqual(
            events[0].details["source_plugin_key"],
            "orcaslicer_hole_reinforcement-0.1.0-py3-none-any",
        )

    def test_on_load_does_nothing_once_the_host_holds_a_config(self):
        # ホストが既定値を初期投入したあと、あるいは利用者が保存したあとの再読み込み。
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability(json.dumps(self.stored_config()))

        capability.on_load()

        self.assertEqual(self.saved, [])
        self.assertEqual(self.diagnostics.events, [])

    def test_on_load_reports_a_missing_donor_without_storing(self):
        self.write_host_config({})
        capability = self.build_capability()

        capability.on_load()

        self.assertEqual(self.saved, [])
        events = self.events("config_migration_skipped")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].details["reason"], "no_donor")

    def test_on_load_reports_an_unreadable_host_config_without_storing(self):
        self.config_path.write_text("{ not json", encoding="utf-8")
        capability = self.build_capability()

        capability.on_load()

        self.assertEqual(self.saved, [])
        events = self.events("config_migration_failed")
        self.assertEqual(len(events), 1)
        # 他テストがパッケージを再importするとenumの同一性が崩れるため値で比較する。
        self.assertEqual(events[0].level.value, DiagnosticLevel.WARNING.value)

    def test_on_load_records_a_failed_store(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability(save_result=False)

        capability.on_load()

        events = self.events("config_migrated")
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].details["stored"])

    def test_on_load_never_raises(self):
        """on_load()が送出するとプラグインの読み込み自体が失敗する。"""
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability()

        def explode(_config_str):
            raise ValueError("host refused")

        capability.save_config = explode
        capability.on_load()

        self.assertEqual(self.events("config_migrated"), [])

    def test_on_load_records_migration_even_when_diagnostics_are_disabled(self):
        self.write_host_config(self.stored_config(diagnostics_enabled=False))
        capability = self.build_capability()

        capability.on_load()

        self.assertEqual(len(self.events("config_migrated")), 1)

    def test_on_load_treats_a_blank_host_config_as_unsaved(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        for raw in ("", "   ", "null"):
            with self.subTest(raw=raw):
                self.saved.clear()
                self.build_capability(raw).on_load()
                self.assertEqual(len(self.saved), 1)

    def test_host_without_save_config_does_not_break_the_load(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.module.HoleReinforcementCapability()
        capability.get_config = lambda: "{}"
        capability._host_config_path_override = self.config_path
        capability._diagnostic_sink_override = self.diagnostics

        capability.on_load()

        events = self.events("config_migrated")
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].details["stored"])

    def test_execute_uses_the_stored_config(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability(
            json.dumps(self.stored_config(reinforcement_width_mm=1.25))
        )

        self.assertEqual(
            capability._resolve_config().config.reinforcement_width_mm, 1.25
        )

    def test_execute_falls_back_to_migration_when_the_host_holds_nothing(self):
        # 保存にも初期投入にも失敗したホスト。スライスを止めずに引き継ぎ値で動く。
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability()

        validation = capability._resolve_config()
        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.config.reinforcement_width_mm, 3.5)

    def test_execute_does_not_emit_migration_events(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability()
        capability.on_load()
        self.diagnostics.events.clear()
        capability.get_config = lambda: json.dumps(self.stored_config())
        self.run_detect(capability, times=3)

        codes = [event.code for event in self.diagnostics.events]
        self.assertNotIn("config_migrated", codes)
        self.assertNotIn("config_migration_skipped", codes)

    def test_invalid_host_config_is_reported_as_validation_error(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability("{ not json")

        validation = capability._resolve_config()
        self.assertFalse(validation.is_valid)
        self.assertIn("not valid JSON", validation.summary())

    def test_unknown_key_in_stored_config_is_not_replaced_by_migration(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability('{"unexpected": true}')

        self.assertFalse(capability._resolve_config().is_valid)

    def test_concurrent_execute_resolves_the_migration_once(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))
        capability = self.build_capability()
        resolved = []
        original = self.module.migrate_config

        def counting(*args, **kwargs):
            resolved.append(1)
            return original(*args, **kwargs)

        ctx = self.detect_context()
        with patch.object(self.module, "migrate_config", counting):
            with patch.object(
                self.module, "extract_transformed_volumes", return_value=()
            ):
                threads = [
                    threading.Thread(target=capability.execute, args=(ctx,))
                    for _ in range(8)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

        self.assertEqual(len(resolved), 1)

    def preset_bundle(self, overrides):
        """`orca.host.preset_bundle()`が返す読み取り専用プリセットを差し替える。"""
        preset = types.SimpleNamespace(
            config_value=lambda key: overrides.get(key)
        )
        sys.modules["orca"].host.preset_bundle = lambda: types.SimpleNamespace(
            current_process_preset=lambda: preset
        )

    def stale_override(self, plugin_key):
        """ホストは`ConfigOptionString::serialize()`のエスケープを掛けて返す。"""
        entries = json.dumps(
            [
                {
                    "capability": "Hole Reinforcement",
                    "capability_type": "slicing-pipeline",
                    "plugin_key": plugin_key,
                    "plugin_version": "0.1.0",
                    "cap_config": {"reinforcement_width_mm": 5},
                }
            ]
        )
        return escape_string_cstyle(entries)

    def running_plugin_key(self, plugin_key="orcaslicer_hole_reinforcement-0.2.0-py3-none-any"):
        """テストのパッケージは`orca_plugins`配下に無いため、導出結果を差し替える。"""
        return patch.object(self.module, "current_plugin_key", lambda _start: plugin_key)

    def test_preset_scan_records_what_it_read(self):
        old = "orcaslicer_hole_reinforcement-0.1.0-py3-none-any"
        self.preset_bundle(
            {"print_plugin_config_overrides": self.stale_override(old)}
        )
        with self.running_plugin_key():
            self.build_capability(json.dumps(self.stored_config())).get_config_ui()

        events = self.events("preset_scan_completed")
        self.assertEqual(len(events), 1)
        details = events[0].details
        self.assertEqual(details["preset_count"], 1)
        self.assertEqual(
            details["own_plugin_key"], "orcaslicer_hole_reinforcement-0.2.0-py3-none-any"
        )
        self.assertEqual(details["stale_overrides"], [old])
        self.assertEqual(
            details["values"]["print_plugin_config_overrides"]["type"], "str"
        )
        self.assertIsNone(details["values"]["printer_plugin_config_overrides"])

    def test_preset_scan_records_a_swallowed_error(self):
        def raising():
            raise RuntimeError("preset bundle is not available")

        sys.modules["orca"].host.preset_bundle = raising
        self.build_capability(json.dumps(self.stored_config())).get_config_ui()

        events = self.events("preset_scan_completed")
        self.assertEqual(len(events), 1)
        self.assertIn("RuntimeError", events[0].details["error"])
        self.assertEqual(events[0].details["stale_overrides"], [])

    def test_config_ui_warns_about_a_stale_preset_override(self):
        self.preset_bundle(
            {
                "print_plugin_config_overrides": self.stale_override(
                    "orcaslicer_hole_reinforcement-0.1.0-py3-none-any"
                )
            }
        )
        html = self.build_capability(json.dumps(self.stored_config())).get_config_ui()

        self.assertIn("orcaslicer_hole_reinforcement-0.1.0-py3-none-any", html)
        self.assertIn("旧バージョン向けに保存された設定が残っています", html)

    def test_config_ui_has_no_warning_without_a_stale_override(self):
        self.preset_bundle({})
        html = self.build_capability(json.dumps(self.stored_config())).get_config_ui()

        self.assertIn('id="stale-override"', html)
        self.assertIn("role=\"status\" hidden>", html)

    def test_config_ui_survives_a_host_without_presets(self):
        def raising():
            raise RuntimeError("preset bundle is not available")

        sys.modules["orca"].host.preset_bundle = raising
        html = self.build_capability(json.dumps(self.stored_config())).get_config_ui()

        self.assertIn('id="config-form"', html)

    def test_stale_override_is_reported_once_per_session(self):
        self.preset_bundle(
            {
                "print_plugin_config_overrides": self.stale_override(
                    "orcaslicer_hole_reinforcement-0.1.0-py3-none-any"
                )
            }
        )
        capability = self.build_capability(json.dumps(self.stored_config()))
        self.run_detect(capability, times=3)

        events = self.events("preset_override_stale")
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].details["plugin_keys"],
            ["orcaslicer_hole_reinforcement-0.1.0-py3-none-any"],
        )
        self.assertEqual(events[0].level.value, DiagnosticLevel.WARNING.value)

    def test_no_stale_override_event_when_the_preset_is_clean(self):
        self.preset_bundle({})
        capability = self.build_capability(json.dumps(self.stored_config()))
        self.run_detect(capability)

        self.assertEqual(self.events("preset_override_stale"), [])

    def test_config_ui_shows_migrated_values_only_when_the_host_holds_nothing(self):
        self.write_host_config(self.stored_config(reinforcement_width_mm=3.5))

        empty_host = self.build_capability().get_config_ui()
        stored_host = self.build_capability(
            json.dumps(self.stored_config(reinforcement_width_mm=1.25))
        ).get_config_ui()

        self.assertIn(
            '"reinforcement_width_mm": 3.5',
            empty_host.split("var initial =")[1].split(";")[0],
        )
        self.assertIn(
            f"var initial = {json.dumps(HoleReinforcementConfig().to_dict(), ensure_ascii=False)};",
            stored_host,
        )


if __name__ == "__main__":
    unittest.main()
