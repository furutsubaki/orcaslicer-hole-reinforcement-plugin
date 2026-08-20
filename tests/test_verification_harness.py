import json
import math
import tempfile
import unittest
from pathlib import Path

from tools.build_verification_project import (
    ProjectBuildError,
    build_object_map,
    clone_datadir,
    fixture_name_from_object_name,
    parse_object_names,
    select_matrix_fixtures,
)
from tools.compare_slice_output import (
    ComparisonError,
    collect_detection_summary,
    collect_problem_events,
    collect_reinforcement_targets,
    compare_analyses,
    diff_by_type,
    fixture_name_from_marker,
    load_diagnostics,
    normalize_line,
    parse_gcode,
    scan_python_log,
)


def _diagnostic(code, name, level="info", **details):
    payload = {"model_object_name": name, **details}
    return {
        "timestamp": "2026-08-21T00:00:00+00:00",
        "level": level,
        "code": code,
        "message": code,
        "details": payload,
    }


def _matrix_entry(fixture_id, *, printable=True):
    return {
        "id": fixture_id,
        "file": f"{fixture_id}.stl",
        "printable": printable,
        "topology": "closed_two_manifold",
    }


def _full_matrix_entries():
    entries = []
    for shape in ("circle", "hexagon", "octagon"):
        for end_kind in ("through", "blind"):
            for angle in ("0", "30", "45", "60", "90"):
                entries.append(_matrix_entry(f"matrix-{shape}-{end_kind}-{angle}"))
    return entries


class FixtureSelectionTests(unittest.TestCase):
    def test_selects_thirty_printable_matrix_fixtures(self):
        entries = _full_matrix_entries() + [
            _matrix_entry("negative-open-groove", printable=False),
            _matrix_entry("diameter-at-max"),
        ]

        selected = select_matrix_fixtures(entries)

        self.assertEqual(len(selected), 30)
        self.assertTrue(all(entry["id"].startswith("matrix-") for entry in selected))

    def test_excludes_intentionally_non_manifold_matrix_fixtures(self):
        entries = _full_matrix_entries()
        entries.append(_matrix_entry("matrix-broken", printable=False))

        selected = select_matrix_fixtures(entries)

        self.assertNotIn("matrix-broken", [entry["id"] for entry in selected])

    def test_rejects_missing_fixtures(self):
        entries = _full_matrix_entries()[:29]

        with self.assertRaises(ProjectBuildError):
            select_matrix_fixtures(entries)

    def test_rejects_duplicate_fixtures(self):
        entries = _full_matrix_entries()
        entries.append(_matrix_entry("matrix-circle-through-0"))

        with self.assertRaises(ProjectBuildError):
            select_matrix_fixtures(entries)


class ProjectObjectTests(unittest.TestCase):
    def test_parses_object_names_from_model_settings(self):
        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="54">
    <metadata key="name" value="matrix-hexagon-blind-90.stl"/>
    <part id="53" subtype="normal_part">
      <metadata key="name" value="ignored-part-name.stl"/>
    </part>
  </object>
  <object id="60">
    <metadata key="name" value="matrix-circle-through-0.stl"/>
  </object>
</config>
"""

        names = parse_object_names(xml_text)

        self.assertEqual(
            names, ["matrix-hexagon-blind-90.stl", "matrix-circle-through-0.stl"]
        )

    def test_rejects_object_without_name(self):
        xml_text = '<?xml version="1.0"?><config><object id="1"/></config>'

        with self.assertRaises(ProjectBuildError):
            parse_object_names(xml_text)

    def test_object_map_detects_missing_fixture(self):
        with self.assertRaises(ProjectBuildError):
            build_object_map(["matrix-circle-through-0.stl"], ["matrix-circle-blind-0"])

    def test_object_map_detects_duplicate_object(self):
        with self.assertRaises(ProjectBuildError):
            build_object_map(
                ["matrix-circle-through-0.stl", "matrix-circle-through-0.stl"],
                ["matrix-circle-through-0"],
            )

    def test_strips_stl_suffix(self):
        self.assertEqual(
            fixture_name_from_object_name("matrix-circle-through-0.stl"),
            "matrix-circle-through-0",
        )


class CloneDatadirTests(unittest.TestCase):
    def test_rejects_destination_equal_to_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "datadir"
            source.mkdir()

            with self.assertRaises(ProjectBuildError):
                clone_datadir(source, source)

    def test_rejects_destination_inside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "datadir"
            source.mkdir()

            with self.assertRaises(ProjectBuildError):
                clone_datadir(source, source / "work" / "datadir")

    def test_rejects_destination_containing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "outer" / "datadir"
            source.mkdir(parents=True)

            with self.assertRaises(ProjectBuildError):
                clone_datadir(source, Path(directory) / "outer")

    def test_copies_into_a_separate_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "datadir"
            (source / "orca_plugins").mkdir(parents=True)
            (source / "orca_plugins" / "config.json").write_text("{}", encoding="utf-8")
            destination = Path(directory) / "work" / "datadir"

            clone_datadir(source, destination)

            self.assertTrue((destination / "orca_plugins" / "config.json").is_file())


class FixtureNameTests(unittest.TestCase):
    def test_restores_name_from_exclude_object_marker(self):
        self.assertEqual(
            fixture_name_from_marker("matrix-circle-through-0.stl_id_0_copy_0"),
            "matrix-circle-through-0",
        )

    def test_restores_name_with_fractional_angle(self):
        self.assertEqual(
            fixture_name_from_marker("direction-circle-through-0.1.stl_id_0_copy_0"),
            "direction-circle-through-0.1",
        )
        self.assertEqual(
            fixture_name_from_marker("direction-circle-through-89.9.stl_id_2_copy_3"),
            "direction-circle-through-89.9",
        )

    def test_restores_name_from_plain_stl_name(self):
        self.assertEqual(
            fixture_name_from_marker("matrix-hexagon-blind-45.stl"),
            "matrix-hexagon-blind-45",
        )


class GcodeParsingTests(unittest.TestCase):
    def test_absolute_extrusion_uses_difference_from_previous_value(self):
        text = "\n".join(
            [
                "M82",
                ";LAYER_CHANGE",
                ";Z:0.2",
                ";TYPE:Outer wall",
                "G1 X10 Y0 E5",
                "G1 X10 Y10 E8",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Outer wall")]

        self.assertAlmostEqual(stats.extrusion_mm, 8.0)
        self.assertAlmostEqual(stats.extrude_distance_mm, 20.0)
        self.assertEqual(stats.extrude_moves, 2)

    def test_relative_extrusion_accumulates_each_move(self):
        text = "\n".join(
            [
                "M83",
                ";LAYER_CHANGE",
                ";TYPE:Inner wall",
                "G1 X10 Y0 E5",
                "G1 X10 Y10 E5",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Inner wall")]

        self.assertAlmostEqual(stats.extrusion_mm, 10.0)

    def test_g92_resets_the_extruder_baseline(self):
        text = "\n".join(
            [
                "M82",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X10 Y0 E5",
                "G92 E0",
                "G1 X20 Y0 E3",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Outer wall")]

        self.assertAlmostEqual(stats.extrusion_mm, 8.0)

    def test_absolute_extrusion_baseline_survives_object_boundaries(self):
        text = "\n".join(
            [
                "M82",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "EXCLUDE_OBJECT_START NAME=a.stl_id_0_copy_0",
                "G1 X10 Y0 E5",
                "EXCLUDE_OBJECT_END NAME=a.stl_id_0_copy_0",
                "EXCLUDE_OBJECT_START NAME=b.stl_id_0_copy_0",
                "G1 X20 Y0 E7",
                "EXCLUDE_OBJECT_END NAME=b.stl_id_0_copy_0",
            ]
        )

        analysis = parse_gcode(text)

        self.assertAlmostEqual(analysis.stats[("a", 0, "Outer wall")].extrusion_mm, 5.0)
        self.assertAlmostEqual(analysis.stats[("b", 0, "Outer wall")].extrusion_mm, 2.0)

    def test_separates_travel_and_retraction_from_extrusion(self):
        text = "\n".join(
            [
                "M83",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X10 Y0 E1",
                "G1 E-0.8",
                "G1 X20 Y0",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Outer wall")]

        self.assertAlmostEqual(stats.extrusion_mm, 1.0)
        self.assertAlmostEqual(stats.extrude_distance_mm, 10.0)
        self.assertAlmostEqual(stats.retraction_mm, 0.8)
        self.assertAlmostEqual(stats.travel_distance_mm, 10.0)

    def test_arc_move_uses_arc_length_not_chord(self):
        text = "\n".join(
            [
                "M83",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X1 Y0",
                "G3 X0 Y1 I-1 J0 E1",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Outer wall")]

        self.assertAlmostEqual(stats.extrude_distance_mm, math.pi / 2, places=6)

    def test_clockwise_arc_sweeps_the_other_way(self):
        text = "\n".join(
            [
                "M83",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X1 Y0",
                "G2 X0 Y1 I-1 J0 E1",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Outer wall")]

        self.assertAlmostEqual(
            stats.extrude_distance_mm, 3.0 * math.pi / 2, places=6
        )

    def test_full_circle_arc_sweeps_the_whole_circumference(self):
        text = "\n".join(
            [
                "M83",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X1 Y0",
                "G3 X1 Y0 I-1 J0 E1",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Outer wall")]

        self.assertAlmostEqual(stats.extrude_distance_mm, 2.0 * math.pi, places=6)

    def test_arc_with_radius_form_is_rejected(self):
        text = "\n".join([";LAYER_CHANGE", ";TYPE:Outer wall", "G2 X1 Y1 R5 E1"])

        with self.assertRaises(ComparisonError):
            parse_gcode(text)

    def test_relative_positioning_offsets_from_current_point(self):
        text = "\n".join(
            [
                "M83",
                "G91",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X10 E1",
                "G1 X10 E1",
            ]
        )

        analysis = parse_gcode(text)
        stats = analysis.stats[(None, 0, "Outer wall")]

        self.assertAlmostEqual(stats.extrude_distance_mm, 20.0)

    def test_assigns_moves_to_the_enclosing_object(self):
        text = "\n".join(
            [
                "M83",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X1 Y0 E1",
                "EXCLUDE_OBJECT_START NAME=matrix-circle-through-0.stl_id_0_copy_0",
                "G1 X2 Y0 E1",
                "EXCLUDE_OBJECT_END NAME=matrix-circle-through-0.stl_id_0_copy_0",
                "G1 X3 Y0 E1",
            ]
        )

        analysis = parse_gcode(text)

        self.assertAlmostEqual(
            analysis.stats[("matrix-circle-through-0", 0, "Outer wall")].extrusion_mm,
            1.0,
        )
        self.assertAlmostEqual(analysis.stats[(None, 0, "Outer wall")].extrusion_mm, 2.0)

    def test_rejects_unclosed_object_marker(self):
        text = "\n".join([";LAYER_CHANGE", "EXCLUDE_OBJECT_START NAME=a.stl_id_0_copy_0"])

        with self.assertRaises(ComparisonError):
            parse_gcode(text)

    def test_rejects_orphan_object_end(self):
        text = "\n".join([";LAYER_CHANGE", "EXCLUDE_OBJECT_END NAME=a.stl_id_0_copy_0"])

        with self.assertRaises(ComparisonError):
            parse_gcode(text)

    def test_rejects_mismatched_object_markers(self):
        text = "\n".join(
            [
                "EXCLUDE_OBJECT_START NAME=a.stl_id_0_copy_0",
                "EXCLUDE_OBJECT_END NAME=b.stl_id_0_copy_0",
            ]
        )

        with self.assertRaises(ComparisonError):
            parse_gcode(text)

    def test_rejects_nested_object_markers(self):
        text = "\n".join(
            [
                "EXCLUDE_OBJECT_START NAME=a.stl_id_0_copy_0",
                "EXCLUDE_OBJECT_START NAME=b.stl_id_0_copy_0",
            ]
        )

        with self.assertRaises(ComparisonError):
            parse_gcode(text)

    def test_keeps_multiple_copies_of_the_same_model_together(self):
        text = "\n".join(
            [
                "M83",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "EXCLUDE_OBJECT_START NAME=a.stl_id_0_copy_0",
                "G1 X1 Y0 E1",
                "EXCLUDE_OBJECT_END NAME=a.stl_id_0_copy_0",
                "EXCLUDE_OBJECT_START NAME=a.stl_id_0_copy_1",
                "G1 X2 Y0 E1",
                "EXCLUDE_OBJECT_END NAME=a.stl_id_0_copy_1",
            ]
        )

        analysis = parse_gcode(text)

        self.assertAlmostEqual(analysis.stats[("a", 0, "Outer wall")].extrusion_mm, 2.0)


class NormalizationTests(unittest.TestCase):
    def test_drops_generation_timestamp_and_absolute_paths(self):
        self.assertIsNone(
            normalize_line(
                "; generated by OrcaSlicer 2.5.0-dev on 2026-08-20 at 23:43:52"
            )
        )
        self.assertIsNone(normalize_line("; source_file = /Users/someone/models/a.stl"))
        self.assertEqual(
            normalize_line("; total layer number: 100"), "; total layer number: 100"
        )

    def test_drops_timestamp_without_zero_padding(self):
        self.assertIsNone(
            normalize_line(
                "; generated by Creality_Print V7.0.1.4212 on 2026-8-21 at 1:19:29"
            )
        )

    def test_drops_repeated_extrusion_width_and_plugin_config_dumps(self):
        for line in (
            ";WIDTH:0.42",
            '; print_plugin_config_overrides = [{"cap_config":{}}]',
            '; different_settings_to_system = "plugins;slicing_pipeline_plugin";;',
        ):
            with self.subTest(line=line):
                self.assertIsNone(normalize_line(line))

    def test_keeps_layer_height(self):
        self.assertEqual(normalize_line(";HEIGHT:0.2"), ";HEIGHT:0.2")

    def test_keeps_movement_commands(self):
        self.assertEqual(normalize_line("G1 X1 Y0 E1"), "G1 X1 Y0 E1")
        self.assertEqual(normalize_line("G92 E0"), "G92 E0")

    def test_drops_thumbnail_payload(self):
        text = "\n".join(
            [
                "; thumbnail begin 16x16 128",
                "; AAAABBBBCCCC",
                "; thumbnail end",
                "; total layer number: 100",
            ]
        )

        analysis = parse_gcode(text)

        self.assertEqual(analysis.line_counts[(None, -1)], 1)

    def test_drops_progress_and_derived_totals(self):
        for line in (
            "M73 P12 R9",
            "; filament used [mm] = 651.86",
            "; total filament cost = 0.00",
            "; estimated printing time (normal mode) = 10m 9s",
            "; estimated first layer printing time (normal mode) = 31s",
        ):
            with self.subTest(line=line):
                self.assertIsNone(normalize_line(line))

    def test_keeps_commands_that_merely_start_like_the_progress_command(self):
        self.assertEqual(normalize_line("M730 S1"), "M730 S1")

    def test_progress_lines_are_excluded_from_the_layer_digest(self):
        text = "\n".join(
            [
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "M73 P12 R9",
                "G1 X1 Y0 E1",
            ]
        )

        analysis = parse_gcode(text)

        self.assertEqual(analysis.line_counts[(None, 0)], 3)

    def test_remaining_time_changes_do_not_create_differences(self):
        def build(remaining, extrusion):
            return "\n".join(
                [
                    "M83",
                    ";LAYER_CHANGE",
                    ";TYPE:Outer wall",
                    f"M73 P12 R{remaining}",
                    f"G1 X1 Y0 E{extrusion}",
                ]
            )

        on = parse_gcode(build(20, 1))
        off = parse_gcode(build(9, 1))

        self.assertEqual(on.line_digests, off.line_digests)

    def test_extracts_print_summary(self):
        text = "\n".join(
            [
                "; filament used [mm] = 651.86",
                "; filament used [cm3] = 1.57",
                "; estimated printing time (normal mode) = 10m 9s",
            ]
        )

        summary = parse_gcode(text).summary

        self.assertEqual(summary["filament_used_mm"], "651.86")
        self.assertEqual(summary["filament_used_cm3"], "1.57")
        self.assertEqual(summary["estimated_time"], "10m 9s")

    def test_identical_slices_compare_equal(self):
        text = "\n".join(
            [
                "; generated by OrcaSlicer 2.5.0-dev on 2026-08-20 at 23:43:52",
                ";LAYER_CHANGE",
                ";TYPE:Outer wall",
                "G1 X1 Y0 E1",
            ]
        )
        other = text.replace("23:43:52", "23:59:59")

        self.assertEqual(
            parse_gcode(text).line_digests, parse_gcode(other).line_digests
        )


class DiagnosticLoadingTests(unittest.TestCase):
    def test_rejects_truncated_json_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.jsonl"
            path.write_text(
                json.dumps(_diagnostic("object_detection_completed", "a.stl"))
                + "\n{\"code\": \"broken\"",
                encoding="utf-8",
            )

            with self.assertRaises(ComparisonError):
                load_diagnostics(path)

    def test_reports_when_the_size_cap_is_reached(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.jsonl"
            path.write_text(
                json.dumps(_diagnostic("object_detection_completed", "a.stl")) + "\n",
                encoding="utf-8",
            )

            result = load_diagnostics(path, max_bytes=1024)

            self.assertFalse(result["at_size_cap"])
            self.assertEqual(len(result["events"]), 1)

    def test_flags_a_file_that_hit_the_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.jsonl"
            path.write_text(
                json.dumps(_diagnostic("object_detection_completed", "a.stl")) + "\n",
                encoding="utf-8",
            )

            result = load_diagnostics(path, max_bytes=10)

            self.assertTrue(result["at_size_cap"])


class ReinforcementTargetTests(unittest.TestCase):
    def test_collects_target_layers_per_model(self):
        events = [
            _diagnostic(
                "reinforcement_completed",
                "matrix-circle-through-0.stl",
                reinforced_layer_count=2,
                reinforced_layers=[
                    {"layer_index": 3, "print_z_mm": 0.8, "region_count": 1},
                    {"layer_index": 4, "print_z_mm": 1.0, "region_count": 1},
                ],
            )
        ]

        targets = collect_reinforcement_targets(events)

        self.assertEqual(
            sorted(targets["matrix-circle-through-0"]["layers"]), [3, 4]
        )

    def test_rejects_diagnostics_without_model_name(self):
        events = [
            {
                "level": "info",
                "code": "reinforcement_completed",
                "details": {"print_object_id": 1},
            }
        ]

        with self.assertRaises(ComparisonError):
            collect_reinforcement_targets(events)

    def test_rejects_duplicate_reinforcement_events(self):
        event = _diagnostic(
            "reinforcement_completed",
            "a.stl",
            reinforced_layer_count=0,
            reinforced_layers=[],
        )

        with self.assertRaises(ComparisonError):
            collect_reinforcement_targets([event, event])

    def test_rejects_layer_count_mismatch(self):
        events = [
            _diagnostic(
                "reinforcement_completed",
                "a.stl",
                reinforced_layer_count=5,
                reinforced_layers=[{"layer_index": 1, "print_z_mm": 0.2}],
            )
        ]

        with self.assertRaises(ComparisonError):
            collect_reinforcement_targets(events)

    def test_rejects_missing_fixtures_from_truncated_log(self):
        events = [_diagnostic("object_detection_completed", "a.stl")]

        with self.assertRaises(ComparisonError):
            collect_reinforcement_targets(events, expected_fixtures=["a", "b"])

    def test_accepts_complete_fixture_set(self):
        events = [
            _diagnostic("object_detection_completed", "a.stl"),
            _diagnostic("object_detection_completed", "b.stl"),
        ]

        targets = collect_reinforcement_targets(events, expected_fixtures=["a", "b"])

        self.assertEqual(targets, {})

    def test_collects_detection_counts(self):
        events = [
            _diagnostic(
                "object_detection_completed",
                "a.stl",
                candidate_count=3,
                accepted_count=2,
                excluded_count=1,
            )
        ]

        summary = collect_detection_summary(events)

        self.assertEqual(summary["a"]["accepted_count"], 2)

    def test_collects_warning_and_error_events(self):
        events = [
            _diagnostic("object_detection_completed", "a.stl"),
            _diagnostic("analysis_failed", "a.stl", level="error"),
        ]

        self.assertEqual(len(collect_problem_events(events)), 1)


class ComparisonTests(unittest.TestCase):
    def _analysis(self, extrusion):
        return parse_gcode(
            "\n".join(
                [
                    "M83",
                    ";LAYER_CHANGE",
                    ";TYPE:Internal solid infill",
                    "EXCLUDE_OBJECT_START NAME=a.stl_id_0_copy_0",
                    f"G1 X1 Y0 E{extrusion}",
                    "EXCLUDE_OBJECT_END NAME=a.stl_id_0_copy_0",
                ]
            )
        )

    def test_difference_inside_a_target_layer_is_expected(self):
        on = self._analysis(2)
        off = self._analysis(1)
        targets = {"a": {"layers": {0: {"print_z_mm": 0.2}}}}

        result = compare_analyses(on, off, targets)

        self.assertEqual(result["unexpected"], [])
        self.assertEqual(len(result["expected"]), 1)

    def test_difference_outside_target_layers_is_unexpected(self):
        on = self._analysis(2)
        off = self._analysis(1)
        targets = {"a": {"layers": {7: {"print_z_mm": 1.6}}}}

        result = compare_analyses(on, off, targets)

        self.assertEqual(len(result["unexpected"]), 1)
        self.assertEqual(result["unexpected"][0]["fixture"], "a")

    def test_identical_output_produces_no_difference(self):
        result = compare_analyses(self._analysis(1), self._analysis(1), {})

        self.assertEqual(result["unexpected"], [])
        self.assertEqual(result["expected"], [])

    def test_type_diff_reports_extrusion_delta(self):
        diff = diff_by_type(self._analysis(2), self._analysis(1))

        self.assertAlmostEqual(
            diff["a"]["Internal solid infill"]["delta_extrusion_mm"], 1.0
        )


class PythonLogTests(unittest.TestCase):
    def test_reads_only_after_the_recorded_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "python.log"
            previous = "ImportError: numpy is required\n"
            path.write_text(previous + "RuntimeError: current failure\n", encoding="utf-8")

            entries = scan_python_log(path, offset=len(previous.encode("utf-8")))

            self.assertEqual(len(entries), 1)
            self.assertIn("current failure", entries[0])

    def test_captures_traceback_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "python.log"
            path.write_text(
                "Traceback (most recent call last):\n  File \"a.py\", line 1\nValueError: bad\n",
                encoding="utf-8",
            )

            entries = scan_python_log(path)

            self.assertEqual(len(entries), 1)
            self.assertIn("ValueError", entries[0])

    def test_returns_nothing_for_a_clean_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "python.log"
            path.write_text("plugin loaded\n", encoding="utf-8")

            self.assertEqual(scan_python_log(path), [])


if __name__ == "__main__":
    unittest.main()
