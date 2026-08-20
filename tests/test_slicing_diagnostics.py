import importlib
import sys
import types
import unittest
from unittest.mock import patch

from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.diagnostics import MemoryDiagnosticSink
from orcaslicer_hole_reinforcement.reinforcement import (
    PlanarRegion,
    ReinforcementRegion,
)


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


if __name__ == "__main__":
    unittest.main()
