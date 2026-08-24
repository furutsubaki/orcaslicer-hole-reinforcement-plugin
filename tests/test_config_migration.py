import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orcaslicer_hole_reinforcement.config import (
    CURRENT_SCHEMA_VERSION,
    default_config,
    default_config_dict,
)
from orcaslicer_hole_reinforcement.config_migration import (
    REASON_MIGRATED,
    REASON_NO_DONOR,
    REASON_NO_HOST_CONFIG,
    REASON_UNREADABLE,
    current_plugin_key,
    find_host_config_path,
    find_stale_preset_overrides,
    host_config_is_empty,
    migrate_config,
    parse_host_config,
)

CAPABILITY = "Hole Reinforcement"


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

# 実機のconfig.jsonにあるv1エントリ。min_polygon_sides等を持たない。
LEGACY_CAP_CONFIG = {
    "axis_tolerance_deg": 2.0,
    "circle_radial_tolerance_mm": 0.1,
    "diagnostics_enabled": True,
    "enabled_end_kinds": ["through", "blind"],
    "enabled_shapes": ["circle", "hexagon", "octagon"],
    "max_hole_diameter_mm": 8.0,
    "min_hole_depth_mm": 1.0,
    "min_hole_diameter_mm": 0.5,
    "polygon_angle_tolerance_deg": 2.0,
    "polygon_edge_length_tolerance_percent": 5.0,
    "reinforcement_width_mm": 3.5,
    "schema_version": 1,
    "solid_reinforcement": True,
}

POC_ENTRY = {
    "capability": "Hole Reinforcement Detector PoC",
    "capability_type": "slicing-pipeline",
    "plugin_key": "hole_reinforcement_detector_poc",
    "plugin_version": "0.01",
    "cap_config": {
        "circularity_tolerance": 0.1,
        "extra_perimeters": 0,
        "max_hole_diameter_mm": 10,
    },
}


def entry(plugin_key, plugin_version, cap_config, **overrides):
    result = {
        "capability": CAPABILITY,
        "capability_type": "slicing-pipeline",
        "plugin_key": plugin_key,
        "plugin_version": plugin_version,
        "cap_config": cap_config,
    }
    result.update(overrides)
    return result


class TempTree:
    """`orca_plugins/<whl>/__whl_extracted__/<pkg>/<pkg>/`の実機構造を再現する。"""

    def __init__(self, whl_name="orcaslicer_hole_reinforcement-0.2.0-py3-none-any.whl"):
        self._temp = tempfile.TemporaryDirectory()
        # macOSの/tmpはsymlink。探索側がresolve()するため、期待値も実体に揃える。
        self.data_dir = Path(self._temp.name).resolve()
        self.plugin_dir = self.data_dir / "orca_plugins"
        self.package_dir = (
            self.plugin_dir
            / whl_name
            / "__whl_extracted__"
            / "orcaslicer_hole_reinforcement"
            / "orcaslicer_hole_reinforcement"
        )
        self.package_dir.mkdir(parents=True)

    @property
    def config_path(self):
        return self.plugin_dir / "config.json"

    def write_config(self, entries):
        self.config_path.write_text(
            json.dumps({"config": entries}, ensure_ascii=False), encoding="utf-8"
        )

    def cleanup(self):
        self._temp.cleanup()


class HostConfigEmptyTests(unittest.TestCase):
    def test_empty_representations(self):
        for raw in (None, "", "   ", "{}", " { } ", "null", {}):
            with self.subTest(raw=raw):
                self.assertTrue(host_config_is_empty(raw))
                self.assertIsNone(parse_host_config(raw))

    def test_non_empty_representations(self):
        for raw in ('{"solid_reinforcement": false}', "[]", "not json", 12, {"a": 1}):
            with self.subTest(raw=raw):
                self.assertFalse(host_config_is_empty(raw))
                self.assertIsNotNone(parse_host_config(raw))

    def test_stored_config_is_validated_once(self):
        validation = parse_host_config(json.dumps(default_config_dict()))

        self.assertIsNotNone(validation)
        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.config, default_config())

    def test_invalid_json_is_a_validation_error_not_an_empty_config(self):
        validation = parse_host_config("{ not json")

        self.assertIsNotNone(validation)
        self.assertFalse(validation.is_valid)
        self.assertIn("not valid JSON", validation.summary())

    def test_non_object_json_is_a_validation_error(self):
        for raw in ('""', "[]", "3"):
            with self.subTest(raw=raw):
                validation = parse_host_config(raw)
                self.assertIsNotNone(validation)
                self.assertFalse(validation.is_valid)


class PathResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tree = TempTree()
        self.addCleanup(self.tree.cleanup)

    def test_finds_config_from_extracted_package(self):
        self.tree.write_config([])
        self.assertEqual(
            find_host_config_path(self.tree.package_dir), self.tree.config_path
        )

    def test_finds_config_directly_under_plugin_dir(self):
        self.tree.write_config([])
        nested = self.tree.plugin_dir / "plugin.py"
        self.assertEqual(find_host_config_path(nested), self.tree.config_path)

    def test_missing_config_file(self):
        self.assertIsNone(find_host_config_path(self.tree.package_dir))

    def test_stops_ascending_at_first_plugin_dir(self):
        # 内側のorca_pluginsにconfig.jsonが無ければ、外側のものを拾わない。
        self.tree.write_config([])
        inner = self.tree.package_dir / "orca_plugins" / "nested"
        inner.mkdir(parents=True)
        self.assertIsNone(find_host_config_path(inner))

    def test_no_plugin_dir_in_ancestors(self):
        self.assertIsNone(find_host_config_path(self.tree.data_dir))

    def test_current_plugin_key_strips_whl_suffix(self):
        self.assertEqual(
            current_plugin_key(self.tree.package_dir),
            "orcaslicer_hole_reinforcement-0.2.0-py3-none-any",
        )

    def test_current_plugin_key_without_plugin_dir(self):
        self.assertIsNone(current_plugin_key(self.tree.data_dir))


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tree = TempTree()
        self.addCleanup(self.tree.cleanup)

    def migrate(self):
        return migrate_config(self.tree.package_dir, CAPABILITY)

    def test_migrates_legacy_schema_and_fills_missing_keys(self):
        self.tree.write_config(
            [POC_ENTRY, entry("orcaslicer_hole_reinforcement-0.1.0-py3-none-any", "0.1.0", LEGACY_CAP_CONFIG)]
        )
        migration = self.migrate()

        self.assertEqual(migration.reason, REASON_MIGRATED)
        self.assertEqual(
            migration.source_plugin_key,
            "orcaslicer_hole_reinforcement-0.1.0-py3-none-any",
        )
        self.assertEqual(migration.source_plugin_version, "0.1.0")
        self.assertEqual(migration.config.reinforcement_width_mm, 3.5)
        self.assertEqual(migration.config.max_hole_diameter_mm, 8.0)
        self.assertEqual(migration.config.schema_version, CURRENT_SCHEMA_VERSION)
        # v1に無いキーは既定値で埋まる。
        defaults = default_config()
        self.assertEqual(migration.config.min_polygon_sides, defaults.min_polygon_sides)
        self.assertEqual(migration.config.max_polygon_sides, defaults.max_polygon_sides)

    def test_picks_highest_version(self):
        self.tree.write_config(
            [
                entry("old", "0.1.0", {**LEGACY_CAP_CONFIG, "reinforcement_width_mm": 1.0}),
                entry("newest", "0.10.0", {**LEGACY_CAP_CONFIG, "reinforcement_width_mm": 4.0}),
                entry("middle", "0.9.0", {**LEGACY_CAP_CONFIG, "reinforcement_width_mm": 2.0}),
            ]
        )
        migration = self.migrate()

        self.assertEqual(migration.source_plugin_key, "newest")
        self.assertEqual(migration.config.reinforcement_width_mm, 4.0)

    def test_falls_through_to_next_candidate_when_invalid(self):
        self.tree.write_config(
            [
                entry("newest", "0.9.0", {"reinforcement_width_mm": 999.0}),
                entry("older", "0.1.0", LEGACY_CAP_CONFIG),
            ]
        )
        migration = self.migrate()

        self.assertEqual(migration.reason, REASON_MIGRATED)
        self.assertEqual(migration.source_plugin_key, "older")
        self.assertEqual(migration.rejected_count, 1)

    def test_excludes_other_capability(self):
        self.tree.write_config([POC_ENTRY])
        migration = self.migrate()

        self.assertEqual(migration.reason, REASON_NO_DONOR)
        self.assertEqual(migration.rejected_count, 0)
        self.assertEqual(migration.config, default_config())

    def test_excludes_empty_cap_config(self):
        self.tree.write_config([entry("empty", "0.1.0", {})])
        self.assertEqual(self.migrate().reason, REASON_NO_DONOR)

    def test_excludes_own_plugin_key(self):
        self.tree.write_config(
            [
                entry(
                    "orcaslicer_hole_reinforcement-0.2.0-py3-none-any",
                    "0.2.0",
                    LEGACY_CAP_CONFIG,
                )
            ]
        )
        self.assertEqual(self.migrate().reason, REASON_NO_DONOR)

    def test_excludes_unrelated_capability_type(self):
        self.tree.write_config(
            [entry("other", "0.1.0", LEGACY_CAP_CONFIG, capability_type="gcode")]
        )
        self.assertEqual(self.migrate().reason, REASON_NO_DONOR)

    def test_accepts_entry_without_capability_type(self):
        legacy = entry("legacy", "0.1.0", LEGACY_CAP_CONFIG)
        del legacy["capability_type"]
        self.tree.write_config([legacy])

        migration = self.migrate()
        self.assertEqual(migration.reason, REASON_MIGRATED)
        self.assertEqual(migration.source_plugin_key, "legacy")

    def test_all_candidates_rejected(self):
        self.tree.write_config([entry("broken", "0.1.0", {"unknown_key": 1})])
        migration = self.migrate()

        self.assertEqual(migration.reason, REASON_NO_DONOR)
        self.assertEqual(migration.rejected_count, 1)
        self.assertEqual(migration.config, default_config())

    def test_missing_host_config(self):
        migration = self.migrate()

        self.assertEqual(migration.reason, REASON_NO_HOST_CONFIG)
        self.assertEqual(migration.config, default_config())

    def test_document_without_config_array(self):
        # ホスト側のレイアウトが変わった場合。引き継ぎ元が無いのと同じ扱いにする。
        self.tree.config_path.write_text('{"other": []}', encoding="utf-8")
        self.assertEqual(self.migrate().reason, REASON_NO_DONOR)

    def test_corrupt_json(self):
        self.tree.config_path.write_text("{ not json", encoding="utf-8")
        migration = self.migrate()

        self.assertEqual(migration.reason, REASON_UNREADABLE)
        self.assertEqual(migration.config, default_config())

    def test_oversized_host_config_is_not_read(self):
        self.tree.write_config([entry("old", "0.1.0", LEGACY_CAP_CONFIG)])
        with patch(
            "orcaslicer_hole_reinforcement.config_migration.MAX_HOST_CONFIG_BYTES", 8
        ):
            with patch.object(Path, "read_text", side_effect=AssertionError) as read:
                migration = self.migrate()

        read.assert_not_called()
        self.assertEqual(migration.reason, REASON_UNREADABLE)
        self.assertEqual(migration.config, default_config())

    def test_unexpected_exception_falls_back_to_defaults(self):
        self.tree.write_config([entry("old", "0.1.0", LEGACY_CAP_CONFIG)])
        # 監査フックはPermissionError以外も送出しうる。
        with patch.object(Path, "read_text", side_effect=RuntimeError("blocked")):
            migration = self.migrate()

        self.assertEqual(migration.reason, REASON_UNREADABLE)
        self.assertEqual(migration.config, default_config())

    def test_explicit_config_path_overrides_search(self):
        other = self.tree.data_dir / "elsewhere.json"
        other.write_text(
            json.dumps({"config": [entry("old", "0.1.0", LEGACY_CAP_CONFIG)]}),
            encoding="utf-8",
        )
        migration = migrate_config(
            self.tree.data_dir, CAPABILITY, config_path=other
        )

        self.assertEqual(migration.reason, REASON_MIGRATED)
        self.assertEqual(migration.source_plugin_key, "old")

    def test_migrated_config_round_trips_to_dict(self):
        self.tree.write_config([entry("old", "0.1.0", LEGACY_CAP_CONFIG)])
        migrated = self.migrate().config.to_dict()

        self.assertEqual(set(migrated), set(default_config_dict()))


class StalePresetOverrideTests(unittest.TestCase):
    def override(self, plugin_key, **extra):
        result = {
            "capability": CAPABILITY,
            "capability_type": "slicing-pipeline",
            "plugin_key": plugin_key,
            "plugin_version": "0.1.0",
            "cap_config": {"reinforcement_width_mm": 5},
        }
        result.update(extra)
        return result

    def find(self, entries, own="orcaslicer_hole_reinforcement-0.2.0-py3-none-any"):
        return find_stale_preset_overrides(json.dumps(entries), CAPABILITY, own)

    def test_reports_an_override_left_for_another_version(self):
        stale = self.find([self.override("orcaslicer_hole_reinforcement-0.1.0-py3-none-any")])

        self.assertEqual(stale, ("orcaslicer_hole_reinforcement-0.1.0-py3-none-any",))

    def test_ignores_the_override_for_the_running_version(self):
        own = "orcaslicer_hole_reinforcement-0.2.0-py3-none-any"
        self.assertEqual(self.find([self.override(own)]), ())

    def test_stops_reporting_once_the_override_was_entered_again(self):
        """ホストは古いエントリを消さないため、これを見ないと警告を消せなくなる。"""
        own = "orcaslicer_hole_reinforcement-0.2.0-py3-none-any"
        entries = [
            self.override("orcaslicer_hole_reinforcement-0.1.0-py3-none-any"),
            self.override(own),
        ]

        self.assertEqual(self.find(entries, own=own), ())

    def test_still_reports_when_only_another_capability_was_entered_again(self):
        own = "orcaslicer_hole_reinforcement-0.2.0-py3-none-any"
        entries = [
            self.override("orcaslicer_hole_reinforcement-0.1.0-py3-none-any"),
            self.override(own, capability="Other Capability"),
        ]

        self.assertEqual(
            self.find(entries, own=own),
            ("orcaslicer_hole_reinforcement-0.1.0-py3-none-any",),
        )

    def test_ignores_another_capability(self):
        entry = self.override("other", capability="Hole Reinforcement Detector PoC")
        self.assertEqual(self.find([entry]), ())

    def test_ignores_another_capability_type(self):
        self.assertEqual(self.find([self.override("other", capability_type="gcode")]), ())

    def test_ignores_an_entry_without_cap_config(self):
        entry = self.override("other")
        del entry["cap_config"]
        self.assertEqual(self.find([entry]), ())

    def test_accepts_an_entry_without_capability_type(self):
        entry = self.override("legacy")
        del entry["capability_type"]
        self.assertEqual(self.find([entry]), ("legacy",))

    def test_deduplicates_nothing_but_keeps_order(self):
        stale = self.find([self.override("a"), self.override("b")])
        self.assertEqual(stale, ("a", "b"))

    def test_tolerates_unusable_values(self):
        for raw in (None, "", "not json", "{}", '"text"', 42, [{"x": 1}], [None]):
            with self.subTest(raw=raw):
                self.assertEqual(
                    find_stale_preset_overrides(raw, CAPABILITY, "own"), ()
                )

    def test_reads_the_cstyle_escaped_form_the_host_returns(self):
        """`ConfigOptionString::serialize()`は`escape_string_cstyle()`を掛けて返す。"""
        entries = [self.override("orcaslicer_hole_reinforcement-0.1.0-py3-none-any")]
        escaped = escape_string_cstyle(json.dumps(entries))

        self.assertIn('\\"', escaped)
        self.assertEqual(
            find_stale_preset_overrides(escaped, CAPABILITY, "own"),
            ("orcaslicer_hole_reinforcement-0.1.0-py3-none-any",),
        )

    def test_reads_the_unescaped_form_too(self):
        entries = [self.override("old")]
        self.assertEqual(
            find_stale_preset_overrides(json.dumps(entries), CAPABILITY, "own"),
            ("old",),
        )

    def test_round_trips_escaped_control_characters(self):
        entries = [self.override("old\\path")]
        escaped = escape_string_cstyle(json.dumps(entries))

        self.assertEqual(
            find_stale_preset_overrides(escaped, CAPABILITY, "own"), ("old\\path",)
        )

    def test_accepts_an_already_parsed_list(self):
        stale = find_stale_preset_overrides(
            [self.override("old")], CAPABILITY, "own"
        )
        self.assertEqual(stale, ("old",))


if __name__ == "__main__":
    unittest.main()
