import sys
import types
import unittest


class PackageBoundaryTests(unittest.TestCase):
    def test_package_import_does_not_require_orcaslicer(self):
        self.assertNotIn("orca", sys.modules)

        import orcaslicer_hole_reinforcement

        self.assertEqual(orcaslicer_hole_reinforcement.__version__, "0.1.0")

    def test_pure_interfaces_can_be_used_without_orcaslicer(self):
        from orcaslicer_hole_reinforcement.detection import (
            DetectedHole,
            HoleEndKind,
            HoleShape,
            MeshSnapshot,
        )
        from orcaslicer_hole_reinforcement.diagnostics import (
            DiagnosticEvent,
            DiagnosticLevel,
            NullDiagnosticSink,
        )
        from orcaslicer_hole_reinforcement.end_classification import (
            HoleEndClassifier,
            HoleEndState,
        )
        from orcaslicer_hole_reinforcement.reinforcement import (
            LayerPlane,
            ReinforcementRegion,
        )

        mesh = MeshSnapshot(
            vertices_mm=((0.0, 0.0, 0.0),),
            triangles=((0, 0, 0),),
        )
        hole = DetectedHole(
            shape=HoleShape.CIRCLE,
            end_kind=HoleEndKind.THROUGH,
            center_mm=(0.0, 0.0, 0.0),
            axis=(0.0, 0.0, 1.0),
            diameter_mm=4.0,
            depth_mm=12.0,
            confidence=1.0,
        )
        layer = LayerPlane(index=0, print_z_mm=0.2)
        region = ReinforcementRegion(layer_index=0, regions=())
        sink = NullDiagnosticSink()
        sink.emit(DiagnosticEvent(DiagnosticLevel.INFO, "test", "ok"))
        classifier = HoleEndClassifier()

        self.assertEqual(len(mesh.vertices_mm), 1)
        self.assertEqual(hole.shape, HoleShape.CIRCLE)
        self.assertEqual(layer.index, region.layer_index)
        self.assertIsInstance(classifier, HoleEndClassifier)
        self.assertEqual(HoleEndState.OPEN.value, "open")

    def test_orcaslicer_import_registers_slicing_capability(self):
        registered = []
        orca = types.ModuleType("orca")

        class Base:
            pass

        class SlicingBase:
            pass

        class Step:
            posSlice = object()
            posPrepareInfill = object()

        class ExecutionResult:
            @staticmethod
            def skipped(message=""):
                return ("skipped", message)

            @staticmethod
            def failure(status, message):
                return (status, message)

        def plugin(package_class):
            package_class().register_capabilities()
            return package_class

        orca.base = Base
        orca.plugin = plugin
        orca.register_capability = registered.append
        orca.slicing = types.SimpleNamespace(
            SlicingPipelineCapabilityBase=SlicingBase,
            Step=Step,
        )
        orca.ExecutionResult = ExecutionResult
        orca.PluginResult = types.SimpleNamespace(FatalError="fatal")
        orca.host = types.SimpleNamespace(app_language=lambda: "ja_JP")

        package_modules = [
            name
            for name in sys.modules
            if name == "orcaslicer_hole_reinforcement"
            or name.startswith("orcaslicer_hole_reinforcement.")
        ]
        for name in package_modules:
            del sys.modules[name]
        sys.modules["orca"] = orca

        try:
            import orcaslicer_hole_reinforcement

            self.assertEqual(len(registered), 1)
            self.assertTrue(issubclass(registered[0], SlicingBase))
            self.assertEqual(orcaslicer_hole_reinforcement.__version__, "0.1.0")

            capability = registered[0]()
            self.assertEqual(capability.get_default_config()["schema_version"], 2)
            self.assertTrue(capability.has_config_ui())
            self.assertIn('id="config-form"', capability.get_config_ui())
            self.assertIn("穴補強設定", capability.get_config_ui())
            capability.get_config = lambda: '{"unexpected": true}'
            result = capability.execute(types.SimpleNamespace(step=Step.posSlice))
            self.assertEqual(result[0], "fatal")
            self.assertIn("invalid configuration", result[1])

            capability.get_config = lambda: "{}"
            result = capability.execute(types.SimpleNamespace(step=Step.posSlice))
            self.assertEqual(result[0], "skipped")
        finally:
            del sys.modules["orca"]
            for name in list(sys.modules):
                if name == "orcaslicer_hole_reinforcement" or name.startswith(
                    "orcaslicer_hole_reinforcement."
                ):
                    del sys.modules[name]


if __name__ == "__main__":
    unittest.main()
