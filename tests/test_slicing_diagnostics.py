import importlib
import sys
import types
import unittest
from unittest.mock import patch

from orcaslicer_hole_reinforcement.config import HoleReinforcementConfig
from orcaslicer_hole_reinforcement.diagnostics import MemoryDiagnosticSink


class Base:
    pass


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


if __name__ == "__main__":
    unittest.main()
