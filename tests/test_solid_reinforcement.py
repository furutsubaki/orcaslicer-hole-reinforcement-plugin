import importlib
import sys
import types
import unittest

from orcaslicer_hole_reinforcement.reinforcement import (
    PlanarRegion,
    ReinforcementRegion,
)


class FakeExPolygon:
    def __init__(self, name, *, intersects=()):
        self.name = name
        self.intersects = tuple(intersects)

    def intersection_ex(self, other):
        return list(self.intersects)

    def diff_ex(self, other):
        return [FakeExPolygon(f"{self.name}-remaining")]


class FakeSurface:
    def __init__(self, surface_type, expolygon):
        self.surface_type = surface_type
        self.expolygon = expolygon
        self.thickness = 0.4
        self.bridge_angle = 1.25
        self.extra_perimeters = 2


class FakeCollection:
    def __init__(self, surfaces):
        self.surfaces = list(surfaces)
        self.set_calls = 0

    def set(self, surfaces):
        self.surfaces = list(surfaces)
        self.set_calls += 1


class FakeGeometry:
    def to_host(self, regions):
        return [FakeExPolygon("target") for _ in regions]


def load_module():
    orca = types.ModuleType("orca")
    orca.host = types.SimpleNamespace(
        Surface=FakeSurface,
        stInternal="internal",
        stInternalSolid="internal-solid",
    )
    sys.modules["orca"] = orca
    for name in (
        "orcaslicer_hole_reinforcement.orca_geometry",
        "orcaslicer_hole_reinforcement.solid_reinforcement",
    ):
        sys.modules.pop(name, None)
    return importlib.import_module(
        "orcaslicer_hole_reinforcement.solid_reinforcement"
    )


class SolidReinforcementTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("orca", None)
        for name in (
            "orcaslicer_hole_reinforcement.orca_geometry",
            "orcaslicer_hole_reinforcement.solid_reinforcement",
        ):
            sys.modules.pop(name, None)

    def test_splits_only_internal_surface_and_preserves_attributes(self):
        module = load_module()
        internal = FakeSurface(
            "internal",
            FakeExPolygon("internal", intersects=(FakeExPolygon("reinforced"),)),
        )
        top = FakeSurface("top", FakeExPolygon("top"))
        collection = FakeCollection((internal, top))
        layer = types.SimpleNamespace(
            regions=lambda: [types.SimpleNamespace(fill_surfaces=collection)]
        )
        planned = (
            ReinforcementRegion(0, (PlanarRegion(((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))),)),
        )

        result = module.apply_solid_reinforcement(
            (layer,), planned, FakeGeometry()
        )

        self.assertEqual(result.changed_collections, 1)
        self.assertEqual(result.solid_surfaces, 1)
        self.assertEqual(collection.set_calls, 1)
        self.assertEqual(
            [surface.surface_type for surface in collection.surfaces],
            ["internal", "internal-solid", "top"],
        )
        for surface in collection.surfaces:
            self.assertEqual(surface.thickness, 0.4)
            self.assertEqual(surface.bridge_angle, 1.25)
            self.assertEqual(surface.extra_perimeters, 2)

    def test_does_not_replace_collection_without_intersection(self):
        module = load_module()
        collection = FakeCollection(
            (FakeSurface("internal", FakeExPolygon("internal")),)
        )
        layer = types.SimpleNamespace(
            regions=lambda: [types.SimpleNamespace(fill_surfaces=collection)]
        )
        planned = (
            ReinforcementRegion(0, (PlanarRegion(((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))),)),
        )

        result = module.apply_solid_reinforcement(
            (layer,), planned, FakeGeometry()
        )

        self.assertEqual(result.changed_collections, 0)
        self.assertEqual(collection.set_calls, 0)

    def test_cancellation_does_not_replace_current_collection(self):
        module = load_module()
        collection = FakeCollection(
            (
                FakeSurface(
                    "internal",
                    FakeExPolygon(
                        "internal", intersects=(FakeExPolygon("reinforced"),)
                    ),
                ),
            )
        )
        layer = types.SimpleNamespace(
            regions=lambda: [types.SimpleNamespace(fill_surfaces=collection)]
        )
        planned = (
            ReinforcementRegion(0, (PlanarRegion(((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))),)),
        )

        with self.assertRaises(module.SolidReinforcementCancelled):
            module.apply_solid_reinforcement(
                (layer,), planned, FakeGeometry(), cancelled=lambda: True
            )

        self.assertEqual(collection.set_calls, 0)


if __name__ == "__main__":
    unittest.main()
