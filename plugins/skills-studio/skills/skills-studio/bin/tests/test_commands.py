"""The commands the /skills-studio session runs, through skills-cli's main() as the shell would."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import studio
from sx.state import StudioPaths


def write_skill(root, name, body="# Body\n"):
    path = Path(root) / name / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\nname: {name}\ndescription: \"Does {name} things when asked to.\"\n---\n{body}")
    return path


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.project, self.home = root / "project", root / "home"
        self.close = write_skill(self.project / ".claude" / "skills", "close-feature")
        write_skill(self.project / ".claude" / "skills", "git-finish")
        write_skill(self.home / ".claude" / "skills", "brain-tdd")
        self.paths = StudioPaths(self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = studio.main([*args, "--project", str(self.project), "--home", str(self.home)])
        return code, json.loads(out.getvalue()) if out.getvalue().strip() else None

    def submit(self, task):
        code, made = self.run_cli("task", "submit", json.dumps(task))
        self.assertEqual(code, 0)
        return made

    def test_lease_take_then_refused_for_another(self):
        self.assertEqual(self.run_cli("lease", "take", "--holder", "a")[0], 0)
        code, reply = self.run_cli("lease", "take", "--holder", "b")
        self.assertEqual(code, 1)
        self.assertEqual(reply["held_by"], "a")

    def test_lease_release(self):
        self.run_cli("lease", "take", "--holder", "a")
        self.run_cli("lease", "release", "--holder", "a")
        self.assertEqual(self.run_cli("lease", "take", "--holder", "b")[0], 0)

    def test_tasks_lists_what_is_in_flight(self):
        made = self.submit({"kind": "link", "from": "close-feature", "to": "git-finish"})
        code, listed = self.run_cli("tasks")
        self.assertEqual(code, 0)
        self.assertEqual([t["id"] for t in listed["tasks"]], [made["id"]])

    def test_start_names_the_file_to_change_and_done_files_it(self):
        made = self.submit({"kind": "link", "from": "close-feature", "to": "git-finish"})
        code, started = self.run_cli("task", "start", made["id"])
        self.assertEqual(code, 0)
        self.assertEqual(started["target_file"], str(self.close.resolve()))
        self.assertNotIn("before", started)
        code, finished = self.run_cli("task", "done", made["id"], "--outcome", "done", "--note", "ok")
        self.assertEqual(code, 0)
        self.assertEqual(finished["outcome"], "done")
        self.assertEqual(list(self.paths.done.glob("*.json"))[0].stem, made["id"])

    def test_unknown_task_is_an_error(self):
        code, reply = self.run_cli("task", "start", "20260101T000000Z-link-abc123")
        self.assertEqual(code, 1)
        self.assertIn("no task", reply["error"])

    def test_copy_makes_the_project_skill(self):
        code, made = self.run_cli("copy", "brain-tdd", "tdd-team")
        self.assertEqual(code, 0)
        self.assertTrue(Path(made["path"]).exists())
        self.assertIn("copied_from: brain-tdd", Path(made["path"]).read_text())

    def test_copy_refuses_a_taken_name(self):
        code, reply = self.run_cli("copy", "brain-tdd", "git-finish")
        self.assertEqual(code, 1)
        self.assertIn("taken", reply["error"])


if __name__ == "__main__":
    unittest.main()
