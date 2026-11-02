import subprocess
import unittest
from pathlib import Path

SHIM = Path(__file__).resolve().parents[4] / "bin" / "skills-cli"


class ShimTest(unittest.TestCase):
    def test_help_runs_through_the_shim(self):
        ran = subprocess.run([str(SHIM), "--help"], capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertIn("skills-cli", ran.stdout)


if __name__ == "__main__":
    unittest.main()
