"""The studio's folder keeps itself out of git, so the project's own .gitignore is never touched."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from sx import lease, wirekinds
from sx.state import StudioPaths
from sx.tasks import submit


class SelfIgnoringTest(unittest.TestCase):
    def check_ignored(self, make):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            make(StudioPaths(project))
            status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                    cwd=project, capture_output=True, text=True, check=True).stdout
            self.assertEqual(status, "")

    def test_lease_folder_is_ignored(self):
        self.check_ignored(lambda paths: lease.take(paths, "a"))

    def test_wire_kinds_file_is_ignored(self):
        self.check_ignored(lambda paths: wirekinds.save(paths, {}, [], [], {}))

    def test_inbox_folder_is_ignored(self):
        self.check_ignored(lambda paths: submit(paths, {"kind": "analyse"}, []))


if __name__ == "__main__":
    unittest.main()
