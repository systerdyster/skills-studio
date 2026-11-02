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
        write_skill(self.home / ".claude" / "skills", "my-tdd")
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

    def test_progress_on_an_active_task_shows_in_flight(self):
        made = self.submit({"kind": "analyse"})
        self.run_cli("task", "start", made["id"])
        code, _ = self.run_cli("task", "progress", made["id"], "--note", "judging wires 4/13")
        self.assertEqual(code, 0)
        [listed] = self.run_cli("tasks")[1]["tasks"]
        self.assertEqual((listed["state"], listed["progress"]), ("active", "judging wires 4/13"))

    def test_progress_on_a_task_not_started_is_an_error(self):
        made = self.submit({"kind": "analyse"})
        code, out = self.run_cli("task", "progress", made["id"], "--note", "x")
        self.assertEqual(code, 1)
        self.assertIn("active", out["error"])

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

    def test_kinds_pending_then_saved_then_on_the_graph(self):
        write_skill(self.project / ".claude" / "skills", "ship", "Then run `git-finish`.\n")
        code, found = self.run_cli("kinds", "pending")
        self.assertEqual(code, 0)
        [ship] = found["pending"]
        self.assertEqual(ship["wires"][0]["lines"][0]["text"], "Then run `git-finish`.")
        verdict = {"ship": {"fingerprint": ship["fingerprint"],
                            "wires": {"git-finish": {"kind": "call", "reason": "run `git-finish`"}}}}
        judged = Path(self.tmp.name) / "kinds.json"
        judged.write_text(json.dumps(verdict))
        code, _ = self.run_cli("kinds", "save", str(judged))
        self.assertEqual(code, 0)
        self.assertEqual(self.run_cli("kinds", "pending")[1]["pending"], [])
        _, graph = self.run_cli("graph")
        [wire] = [w for w in graph["wires"] if w["from"] == "ship"]
        self.assertEqual(wire["kind"], "call")

    def test_kinds_save_refuses_a_bad_judgement(self):
        judged = Path(self.tmp.name) / "kinds.json"
        judged.write_text(json.dumps({"my-tdd": {"fingerprint": "x", "wires": {}}}))
        code, out = self.run_cli("kinds", "save", str(judged))
        self.assertEqual(code, 1)
        self.assertIn("project", out["error"])

    def test_insights_saved_show_on_the_graph_until_the_text_changes(self):
        found = Path(self.tmp.name) / "insights.json"
        found.write_text(json.dumps([{"kind": "badly-written", "skills": ["git-finish"],
                                      "message": "Says merge twice, in two ways.", "lines": {"git-finish": [5]}}]))
        self.assertEqual(self.run_cli("insights", "save", str(found)), (0, {"saved": 1}))
        _, graph = self.run_cli("graph")
        self.assertEqual([i["kind"] for i in graph["insights"]], ["badly-written"])
        _, checked = self.run_cli("check")
        self.assertIn("analyse-badly-written", {f["check"] for f in checked["findings"]})
        skill = self.project / ".claude" / "skills" / "git-finish" / "SKILL.md"
        skill.write_text(skill.read_text() + "Fixed.\n")
        self.assertEqual(self.run_cli("insights", "show")[1], {"insights": []})

    def test_insights_save_refuses_an_unknown_kind(self):
        found = Path(self.tmp.name) / "insights.json"
        found.write_text(json.dumps([{"kind": "vibes", "skills": ["git-finish"], "message": "x"}]))
        code, out = self.run_cli("insights", "save", str(found))
        self.assertEqual(code, 1)
        self.assertIn("kind", out["error"])

    def test_stop_without_a_running_studio_says_so(self):
        self.assertEqual(self.run_cli("stop"), (0, {"stopped": False}))

    def test_copy_makes_the_project_skill(self):
        code, made = self.run_cli("copy", "my-tdd", "tdd-team")
        self.assertEqual(code, 0)
        self.assertTrue(Path(made["path"]).exists())
        self.assertIn("copied_from: my-tdd", Path(made["path"]).read_text())

    def test_copy_refuses_a_taken_name(self):
        code, reply = self.run_cli("copy", "my-tdd", "git-finish")
        self.assertEqual(code, 1)
        self.assertIn("taken", reply["error"])


if __name__ == "__main__":
    unittest.main()
