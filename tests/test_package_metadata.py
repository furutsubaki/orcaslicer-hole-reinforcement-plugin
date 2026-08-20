import tomllib
import unittest
from pathlib import Path


class PackageMetadataTests(unittest.TestCase):
    def test_declares_numpy_for_orcaslicer_geometry_arrays(self):
        project_root = Path(__file__).resolve().parents[1]
        with (project_root / "pyproject.toml").open("rb") as stream:
            metadata = tomllib.load(stream)

        self.assertIn("numpy", metadata["project"]["dependencies"])


if __name__ == "__main__":
    unittest.main()
