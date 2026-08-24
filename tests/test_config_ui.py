import json
import re
import unittest

from orcaslicer_hole_reinforcement.config import default_config_dict
from orcaslicer_hole_reinforcement.config_ui import render_config_ui


class ConfigUiTests(unittest.TestCase):
    def test_all_editable_settings_have_controls(self):
        html = render_config_ui()

        for key, value in default_config_dict().items():
            if key == "schema_version":
                self.assertIn("Configuration format:</strong> v2", html)
            elif isinstance(value, list):
                self.assertIn(f'name="{key}"', html)
            else:
                self.assertIn(f'id="{key}"', html)

    def test_shows_the_real_version_because_the_plugin_list_shows_a_fixed_one(self):
        from orcaslicer_hole_reinforcement.version import __version__

        for language in ("ja", "en"):
            with self.subTest(language=language):
                html = render_config_ui(language)

                self.assertIn(f'<span class="version">{__version__}</span>', html)
                self.assertNotRegex(html, r"__[A-Z_]+__")

    def test_ui_uses_orcaslicer_config_bridge(self):
        html = render_config_ui()

        self.assertIn("window.orca.saveConfig(config)", html)
        self.assertIn("window.orca.restoreDefaults()", html)
        self.assertIn("window.orca.onConfig(receiveConfig)", html)
        self.assertIn('form.addEventListener("input", persistIfValid)', html)
        self.assertNotIn('id="save"', html)
        self.assertIn("Valid changes are saved automatically.", html)

    def test_interactive_controls_have_accessible_names(self):
        html = render_config_ui()

        for key in (
            "min_hole_diameter_mm",
            "max_hole_diameter_mm",
            "reinforcement_width_mm",
            "min_hole_depth_mm",
            "min_polygon_sides",
            "max_polygon_sides",
            "circle_radial_tolerance_mm",
            "polygon_edge_length_tolerance_percent",
            "polygon_angle_tolerance_deg",
            "axis_tolerance_deg",
            "solid_reinforcement",
            "diagnostics_enabled",
        ):
            self.assertIn(f'<label for="{key}">', html)

        self.assertIn('role="group" aria-labelledby="shapes-label"', html)
        self.assertIn('role="group" aria-labelledby="ends-label"', html)
        self.assertIn('role="alert" aria-live="assertive"', html)

    def test_japanese_and_english_follow_supported_language_codes(self):
        japanese = render_config_ui("ja_JP")
        english = render_config_ui("en_US")

        self.assertIn('lang="ja"', japanese)
        self.assertIn('document.documentElement.lang = "ja"', japanese)
        self.assertIn("穴補強設定", japanese)
        self.assertIn("最小穴径は最大穴径以下にしてください。", japanese)
        self.assertIn('lang="en"', english)
        self.assertIn('document.documentElement.lang = "en"', english)
        self.assertIn("Hole reinforcement settings", english)
        self.assertIn(
            "Minimum hole diameter must not exceed maximum hole diameter.", english
        )

    def test_unsupported_or_missing_language_falls_back_to_english(self):
        for language in ("", "fr_FR", "zh_CN", None, 42):
            with self.subTest(language=language):
                html = render_config_ui(language)
                self.assertIn('lang="en"', html)
                self.assertIn("Hole reinforcement settings", html)

    def test_theme_uses_orcaslicer_host_contract(self):
        html = render_config_ui()

        for variable in (
            "--orca-bg",
            "--orca-fg",
            "--orca-muted",
            "--orca-border",
            "--orca-accent",
            "--orca-accent-fg",
            "--orca-font",
        ):
            self.assertIn(f"var({variable}", html)

        self.assertNotIn("--orca-background", html)
        self.assertNotIn("--orca-text-secondary", html)

    def test_initial_config_defaults_to_default_config(self):
        html = render_config_ui()

        expected = json.dumps(default_config_dict(), ensure_ascii=False)
        self.assertIn(f"var initial = {expected};", html)

    def test_initial_config_carries_migrated_values(self):
        migrated = {**default_config_dict(), "reinforcement_width_mm": 3.5}
        html = render_config_ui("ja_JP", migrated)

        self.assertIn(
            f"var initial = {json.dumps(migrated, ensure_ascii=False)};", html
        )
        self.assertIn(
            f"var defaults = {json.dumps(default_config_dict(), ensure_ascii=False)};",
            html,
        )

    def test_initial_config_is_used_only_when_host_config_is_empty(self):
        html = render_config_ui()

        self.assertIn(
            "var initialValid = populate(hasValues(config) ? config : initial);", html
        )
        self.assertIn("return !!config && Object.keys(config).length > 0;", html)

    def test_initial_config_escapes_markup_like_defaults(self):
        html = render_config_ui("en_US", {"enabled_shapes": ["</script>"]})

        self.assertIn('var initial = {"enabled_shapes": ["\\u003c/script>"]};', html)

    def test_stale_override_notice_is_hidden_by_default(self):
        html = render_config_ui("ja_JP")

        self.assertIn('id="stale-override"', html)
        self.assertIn('role="status" hidden>', html)

    def test_stale_override_notice_lists_the_affected_plugin_keys(self):
        html = render_config_ui("ja_JP", None, ("a-0.1.0", "b-0.2.0"))

        self.assertIn("旧バージョン向けに保存された設定が残っています", html)
        self.assertIn("<code>a-0.1.0/ b-0.2.0</code>", html)
        self.assertNotIn('role="status" hidden>', html)

    def test_stale_override_notice_escapes_plugin_keys(self):
        html = render_config_ui("en_US", None, ("<img src=x>",))

        self.assertIn("&lt;img src=x&gt;", html)

    def test_stale_override_notice_ignores_non_string_keys(self):
        html = render_config_ui("en_US", None, (None, 12))

        self.assertIn('role="status" hidden>', html)

    def test_rendered_ui_has_no_unresolved_template_tokens(self):
        for language in ("en_US", "ja_JP"):
            with self.subTest(language=language):
                self.assertIsNone(re.search(r"__[A-Z][A-Z_]*__", render_config_ui(language)))


if __name__ == "__main__":
    unittest.main()
