import unittest
import re

from orcaslicer_hole_reinforcement.config import default_config_dict
from orcaslicer_hole_reinforcement.config_ui import render_config_ui


class ConfigUiTests(unittest.TestCase):
    def test_all_editable_settings_have_controls(self):
        html = render_config_ui()

        for key, value in default_config_dict().items():
            if key == "schema_version":
                self.assertIn("Configuration format:</strong> v1", html)
            elif isinstance(value, list):
                self.assertIn(f'name="{key}"', html)
            else:
                self.assertIn(f'id="{key}"', html)

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

    def test_rendered_ui_has_no_unresolved_template_tokens(self):
        for language in ("en_US", "ja_JP"):
            with self.subTest(language=language):
                self.assertIsNone(re.search(r"__[A-Z][A-Z_]*__", render_config_ui(language)))


if __name__ == "__main__":
    unittest.main()
