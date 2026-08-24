import importlib.util
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocLinkCheckTests(unittest.TestCase):
    def setUp(self):
        self.module = load("check_doc_links")

    def test_committed_documents_have_no_broken_links(self):
        broken = {
            document.relative_to(PROJECT_ROOT).as_posix(): targets
            for document in self.module.documents()
            if (targets := self.module.broken_links(document))
        }

        self.assertEqual(broken, {})

    def test_reports_a_missing_target(self):
        document = PROJECT_ROOT / "docs" / "configuration.md"
        with self.subTest("既存のリンクは通る"):
            self.assertEqual(self.module.broken_links(document), [])

    def test_ignores_external_links_and_anchors(self):
        document = PROJECT_ROOT / "README.md"
        text = document.read_text(encoding="utf-8")

        self.assertIn("https://", text)
        self.assertEqual(self.module.broken_links(document), [])


class ChangelogExtractionTests(unittest.TestCase):
    def setUp(self):
        self.module = load("extract_changelog")
        self.changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    def test_extracts_the_requested_version_only(self):
        section = self.module.extract(self.changelog, "1.0.0")

        self.assertIsNotNone(section)
        self.assertNotIn("## [", section)
        self.assertIn("### 追加", section)

    def test_drops_reference_link_definitions(self):
        """Releaseの本文へそのまま貼るため、末尾のリンク定義を残さない。"""
        section = self.module.extract(self.changelog, "1.0.0")

        self.assertNotIn("[Unreleased]:", section)
        self.assertNotIn("[1.0.0]:", section)

    def test_returns_none_for_an_unknown_version(self):
        self.assertIsNone(self.module.extract(self.changelog, "9.9.9"))

    def test_stops_at_the_next_version_heading(self):
        text = "## [2.0.0]\n\nnew\n\n## [1.0.0]\n\nold\n"

        self.assertEqual(self.module.extract(text, "2.0.0"), "new\n")
        self.assertEqual(self.module.extract(text, "1.0.0"), "old\n")


class ContinuousIntegrationTests(unittest.TestCase):
    """CIの前提が壊れても気付けるようにする。"""

    def test_pr_check_keeps_the_job_name_the_ruleset_requires(self):
        """ルールセットのrequired_status_checksは"check"を参照する。

        ジョブ名を変えると保護が空振りし、チェックを通さずマージできてしまう。
        """
        workflow = (PROJECT_ROOT / ".github/workflows/pr-check.yml").read_text(
            encoding="utf-8"
        )

        self.assertRegex(workflow, r"(?m)^jobs:\n(?:.*\n)*?  check:$")

    def test_ci_requirements_cover_every_runtime_dependency(self):
        """pyprojectへ依存を足してrequirements-ci.txtを忘れると、CIだけが落ちる。"""
        import tomllib

        with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
            declared = tomllib.load(stream)["project"]["dependencies"]
        pinned = (PROJECT_ROOT / "requirements-ci.txt").read_text(encoding="utf-8")

        for dependency in declared:
            name = re.split(r"[<>=!~\[ ]", dependency, maxsplit=1)[0]
            with self.subTest(dependency=name):
                self.assertRegex(pinned, rf"(?mi)^{re.escape(name)}==")


if __name__ == "__main__":
    unittest.main()
