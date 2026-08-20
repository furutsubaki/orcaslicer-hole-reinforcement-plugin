import json
import math
import unittest

from orcaslicer_hole_reinforcement.config import (
    CURRENT_SCHEMA_VERSION,
    default_config,
    default_config_dict,
    parse_config,
    parse_json_config,
)


class ConfigValidationTests(unittest.TestCase):
    def test_missing_keys_use_defaults(self):
        validation = parse_config({})

        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.config, default_config())

    def test_default_config_is_json_serializable(self):
        encoded = json.dumps(default_config_dict())

        self.assertTrue(parse_json_config(encoded).is_valid)

    def test_numeric_boundaries_are_inclusive(self):
        boundaries = {
            "min_hole_diameter_mm": (0.1, 100.0),
            "max_hole_diameter_mm": (0.1, 100.0),
            "reinforcement_width_mm": (0.1, 20.0),
            "min_hole_depth_mm": (0.1, 1000.0),
            "circle_radial_tolerance_mm": (0.0, 1.0),
            "polygon_edge_length_tolerance_percent": (0.0, 25.0),
            "polygon_angle_tolerance_deg": (0.0, 15.0),
            "axis_tolerance_deg": (0.0, 15.0),
        }

        for key, (minimum, maximum) in boundaries.items():
            for value in (minimum, maximum):
                supplied = {key: value}
                if key == "min_hole_diameter_mm" and value > 10.0:
                    supplied["max_hole_diameter_mm"] = value
                if key == "max_hole_diameter_mm" and value < 0.5:
                    supplied["min_hole_diameter_mm"] = value
                with self.subTest(key=key, value=value):
                    self.assertTrue(parse_config(supplied).is_valid)

    def test_numeric_values_outside_boundaries_are_rejected(self):
        boundaries = {
            "min_hole_diameter_mm": (0.1, 100.0),
            "max_hole_diameter_mm": (0.1, 100.0),
            "reinforcement_width_mm": (0.1, 20.0),
            "min_hole_depth_mm": (0.1, 1000.0),
            "circle_radial_tolerance_mm": (0.0, 1.0),
            "polygon_edge_length_tolerance_percent": (0.0, 25.0),
            "polygon_angle_tolerance_deg": (0.0, 15.0),
            "axis_tolerance_deg": (0.0, 15.0),
        }

        for key, (minimum, maximum) in boundaries.items():
            for value in (minimum - 0.01, maximum + 0.01):
                with self.subTest(key=key, value=value):
                    validation = parse_config({key: value})
                    self.assertFalse(validation.is_valid)
                    self.assertIn(
                        "range", {issue.code for issue in validation.issues}
                    )

    def test_non_finite_and_boolean_numbers_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value):
                self.assertFalse(
                    parse_config({"max_hole_diameter_mm": value}).is_valid
                )

    def test_unknown_keys_are_rejected(self):
        validation = parse_config({"unexpected": 1})

        self.assertFalse(validation.is_valid)
        self.assertEqual(validation.issues[0].code, "unknown")

    def test_invalid_root_and_json_are_rejected(self):
        for supplied in (None, [], "text"):
            with self.subTest(supplied=supplied):
                self.assertFalse(parse_config(supplied).is_valid)

        self.assertFalse(parse_json_config("{").is_valid)
        self.assertFalse(parse_json_config(None).is_valid)

    def test_invalid_boolean_is_rejected(self):
        for value in (0, 1, "true", None):
            with self.subTest(value=value):
                self.assertFalse(
                    parse_config({"solid_reinforcement": value}).is_valid
                )

    def test_choice_lists_are_validated_and_normalized(self):
        validation = parse_config(
            {
                "enabled_shapes": ["octagon", "circle"],
                "enabled_end_kinds": ["blind"],
            }
        )

        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.config.enabled_shapes, ("circle", "octagon"))
        self.assertEqual(validation.config.enabled_end_kinds, ("blind",))

        for value in ([], "circle", ["circle", "circle"], ["triangle"], [1]):
            with self.subTest(value=value):
                self.assertFalse(parse_config({"enabled_shapes": value}).is_valid)

    def test_polygon_side_boundaries_and_relation_are_validated(self):
        for key in ("min_polygon_sides", "max_polygon_sides"):
            for value in (3, 64):
                supplied = {key: value}
                if key == "min_polygon_sides" and value == 64:
                    supplied["max_polygon_sides"] = 64
                if key == "max_polygon_sides" and value == 3:
                    supplied["min_polygon_sides"] = 3
                self.assertTrue(parse_config(supplied).is_valid)
            for value in (2, 65, 3.0, True):
                self.assertFalse(parse_config({key: value}).is_valid)

        validation = parse_config(
            {"min_polygon_sides": 13, "max_polygon_sides": 12}
        )
        self.assertFalse(validation.is_valid)
        self.assertIn("relation", {issue.code for issue in validation.issues})

    def test_diameter_relation_is_validated(self):
        validation = parse_config(
            {"min_hole_diameter_mm": 5.0, "max_hole_diameter_mm": 4.0}
        )

        self.assertFalse(validation.is_valid)
        self.assertIn("relation", {issue.code for issue in validation.issues})

    def test_schema_version_policy(self):
        self.assertTrue(parse_config({}).is_valid)
        self.assertTrue(
            parse_config({"schema_version": CURRENT_SCHEMA_VERSION}).is_valid
        )

        migrated = parse_config({"schema_version": 1})
        self.assertTrue(migrated.is_valid)
        self.assertEqual(migrated.config.schema_version, CURRENT_SCHEMA_VERSION)

        for value in (0, CURRENT_SCHEMA_VERSION + 1, "1", True):
            with self.subTest(value=value):
                self.assertFalse(parse_config({"schema_version": value}).is_valid)


if __name__ == "__main__":
    unittest.main()
