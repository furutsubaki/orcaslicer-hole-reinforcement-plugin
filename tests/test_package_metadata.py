import tomllib
import unittest
from pathlib import Path

from orcaslicer_hole_reinforcement.version import __version__, __wheel_version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _metadata():
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)


class PackageMetadataTests(unittest.TestCase):
    def test_declares_numpy_for_orcaslicer_geometry_arrays(self):
        self.assertIn("numpy", _metadata()["project"]["dependencies"])

    def test_wheel_version_is_the_major_of_the_real_version(self):
        """wheelのstemがplugin_keyになるため、メジャー以外で動かしてはいけない。"""
        major = __version__.split(".")[0]

        self.assertEqual(__wheel_version__, major)

    def test_build_reads_the_wheel_version_not_the_real_one(self):
        version = _metadata()["tool"]["hatch"]["version"]

        self.assertIn("version", _metadata()["project"]["dynamic"])
        self.assertEqual(version["path"], "src/orcaslicer_hole_reinforcement/version.py")
        self.assertIn("__wheel_version__", version["pattern"])


if __name__ == "__main__":
    unittest.main()
