"""Copying a read-only skill into the project as a template: the whole folder, under a new name,
with its origin recorded so the studio can tell when the source moves on."""

import os
import tempfile
import unittest
from pathlib import Path

from sx.checks import content_hash
from sx.copying import CopyError, copy_skill
from sx.frontmatter import parse


class CopyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.vault = root / "vault" / "tdd"
        self.vault.mkdir(parents=True)
        (self.vault / "reference.md").write_text("extra")
        self.link = root / "home" / "my-tdd"
        self.link.parent.mkdir()
        os.symlink(self.vault, self.link)
        self.project_skills = root / "project" / ".claude" / "skills"

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, text):
        (self.vault / "SKILL.md").write_text(text)
        return {"id": "my-tdd", "name": "my-tdd", "path": str(self.link / "SKILL.md")}

    def test_copy_renames_and_records_its_origin(self):
        text = '---\nname: my-tdd\ndescription: "Test first."\n---\n# Body\n'
        made = copy_skill(self.project_skills, self.source(text), "tdd-team")
        frontmatter, body = parse(made.read_text())
        self.assertEqual(made, self.project_skills / "tdd-team" / "SKILL.md")
        self.assertEqual(frontmatter["name"], "tdd-team")
        self.assertEqual(frontmatter["description"], "Test first.")
        self.assertEqual(frontmatter["metadata"], {"copied_from": "my-tdd", "copied_hash": content_hash(text)})
        self.assertEqual(body, "# Body\n")

    def test_existing_metadata_block_is_extended(self):
        text = "---\nname: my-tdd\ndescription: x y z\nmetadata:\n  type: reference\nlicense: MIT\n---\nbody\n"
        made = copy_skill(self.project_skills, self.source(text), "tdd-team")
        frontmatter, _ = parse(made.read_text())
        self.assertEqual(frontmatter["metadata"]["type"], "reference")
        self.assertEqual(frontmatter["metadata"]["copied_from"], "my-tdd")
        self.assertEqual(frontmatter["license"], "MIT")

    def test_supporting_files_come_along_and_links_are_resolved(self):
        made = copy_skill(self.project_skills, self.source("---\nname: my-tdd\ndescription: x\n---\n"), "tdd-team")
        self.assertEqual((made.parent / "reference.md").read_text(), "extra")
        self.assertFalse(made.parent.is_symlink())

    def test_existing_target_is_refused(self):
        source = self.source("---\nname: my-tdd\ndescription: x\n---\n")
        copy_skill(self.project_skills, source, "tdd-team")
        with self.assertRaises(CopyError):
            copy_skill(self.project_skills, source, "tdd-team")

    def test_source_without_frontmatter_gets_one(self):
        made = copy_skill(self.project_skills, self.source("# Just a body\n"), "tdd-team")
        frontmatter, body = parse(made.read_text())
        self.assertEqual(frontmatter["name"], "tdd-team")
        self.assertEqual(body, "# Just a body\n")


if __name__ == "__main__":
    unittest.main()
