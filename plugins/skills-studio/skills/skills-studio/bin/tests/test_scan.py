"""scan() finds every skill the project can see — its own, the user's, synced ones and installed
plugins' — and describes each one; a skill it cannot read is reported, not skipped."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from sx.scan import scan


def skill(root, folder, text):
    path = Path(root) / folder / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def fm(name, description="Does a thing.", body="# Body\n"):
    return f"---\nname: {name}\ndescription: \"{description}\"\n---\n{body}"


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.project = root / "project"
        self.home = root / "home"
        self.vault = root / "vault"
        self.project_skills = self.project / ".claude" / "skills"
        self.user_skills = self.home / ".claude" / "skills"
        self.project_skills.mkdir(parents=True)
        self.user_skills.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_scan(self):
        return {s["name"]: s for s in scan(self.project, self.home)}

    def test_project_skill_is_described(self):
        skill(self.project_skills, "close-feature", fm("close-feature", "Close a case.", "x" * 400))
        found = self.run_scan()["close-feature"]
        self.assertEqual(found["source"], "project")
        self.assertEqual(found["frontmatter"]["description"], "Close a case.")
        self.assertEqual(found["body"], "x" * 400)
        self.assertGreater(found["size"], 400)
        self.assertRegex(found["modified"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(found["tokens"]["body"], 100)
        self.assertEqual(found["tokens"]["listing"], -(-len("close-feature" "Close a case.") // 4))
        self.assertTrue(found["writable"])
        self.assertIsNone(found["error"])
        self.assertEqual(found["body_line"], 5)

    def test_body_without_frontmatter_starts_on_line_one(self):
        skill(self.project_skills, "bare", "# No frontmatter\n")
        self.assertEqual(self.run_scan()["bare"]["body_line"], 1)

    def test_symlinked_user_skill_is_named_by_its_frontmatter_not_its_folder(self):
        real = skill(self.vault, "code-review", fm("brain-code-review"))
        os.symlink(real.parent, self.user_skills / "brain-code-review-link")
        found = self.run_scan()["brain-code-review"]
        self.assertEqual(found["source"], "user")
        self.assertEqual(found["folder"], "brain-code-review-link")
        self.assertEqual(found["real_path"], str(real.resolve()))
        self.assertFalse(found["writable"])

    def test_skill_without_frontmatter_takes_its_folder_name_and_is_flagged(self):
        skill(self.project_skills, "bare", "# No frontmatter\n")
        found = self.run_scan()["bare"]
        self.assertIsNone(found["frontmatter"])
        self.assertEqual(found["error"], "missing frontmatter")

    def test_broken_frontmatter_is_reported_not_skipped(self):
        skill(self.project_skills, "broken", "---\nname: broken\nnot yaml at all\n---\nbody\n")
        found = self.run_scan()["broken"]
        self.assertIn("line 2", found["error"])
        self.assertIsNone(found["frontmatter"])

    def test_hidden_folders_and_folders_without_skill_md_are_ignored(self):
        skill(self.user_skills / ".trash", "old", fm("old"))
        (self.user_skills / "empty").mkdir()
        self.assertEqual(self.run_scan(), {})

    def test_synced_skills_are_their_own_source(self):
        skill(self.user_skills / "synced" / "abc_123", "docx", fm("docx"))
        self.assertEqual(self.run_scan()["docx"]["source"], "synced")

    def test_plugin_skills_follow_installed_plugins_and_their_scope(self):
        plugins = self.home / ".claude" / "plugins"
        mine = plugins / "cache" / "m" / "mine" / "1.0"
        other = plugins / "cache" / "m" / "other" / "1.0"
        skill(mine / "skills", "helper", fm("helper"))
        skill(other / "skills", "elsewhere", fm("elsewhere"))
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "mine@m": [{"scope": "user", "installPath": str(mine)}],
            "other@m": [{"scope": "project", "projectPath": "/somewhere/else", "installPath": str(other)}],
        }}))
        found = self.run_scan()
        self.assertEqual(found["helper"]["source"], "plugin")
        self.assertEqual(found["helper"]["plugin"], "mine")
        self.assertNotIn("elsewhere", found)

    def test_project_scoped_plugin_counts_in_its_own_project(self):
        plugins = self.home / ".claude" / "plugins"
        here = plugins / "cache" / "m" / "here" / "1.0"
        skill(here / "skills", "local-helper", fm("local-helper"))
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "here@m": [{"scope": "local", "projectPath": str(self.project), "installPath": str(here)}],
        }}))
        self.assertIn("local-helper", self.run_scan())

    def test_missing_folders_give_an_empty_scan(self):
        self.assertEqual(scan(Path(self.tmp.name) / "nowhere", Path(self.tmp.name) / "nohome"), [])


if __name__ == "__main__":
    unittest.main()
