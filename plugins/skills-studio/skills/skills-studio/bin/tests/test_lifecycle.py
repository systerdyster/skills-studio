"""A task's life: waiting in inbox/, taken by the session into active/ with the target's text as it
was, then filed in done/ with an outcome and the text as it became."""

import json
import tempfile
import unittest
from pathlib import Path

from sx.state import StudioPaths
from sx.tasks import TaskError, done, in_flight, new_since, pending, start, submit


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = StudioPaths(root)
        self.skill_file = root / ".claude" / "skills" / "close-feature" / "SKILL.md"
        self.skill_file.parent.mkdir(parents=True)
        self.skill_file.write_text("before text")
        self.skills = [
            {"id": "close-feature", "name": "close-feature", "source": "project", "writable": True,
             "path": str(self.skill_file)},
            {"id": "git-finish", "name": "git-finish", "source": "project", "writable": True,
             "path": str(root / "x" / "SKILL.md")},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def link(self):
        return submit(self.paths, {"kind": "link", "from": "close-feature", "to": "git-finish"}, self.skills)

    def test_pending_lists_inbox_oldest_first(self):
        first, second = self.link(), self.link()
        self.assertEqual([t["id"] for t in pending(self.paths)], [first["id"], second["id"]])

    def test_start_moves_the_task_and_keeps_the_text_before(self):
        task = self.link()
        started = start(self.paths, task["id"], self.skills)
        self.assertEqual(pending(self.paths), [])
        self.assertEqual(started["before"], {str(self.skill_file): "before text"})
        self.assertTrue((self.paths.active / f"{task['id']}.json").exists())
        self.assertIn("started_at", started)

    def test_done_files_the_outcome_and_the_text_after(self):
        task = self.link()
        start(self.paths, task["id"], self.skills)
        self.skill_file.write_text("after text")
        finished = done(self.paths, task["id"], "done", "Added a call in step 2.")
        stored = json.loads((self.paths.done / f"{task['id']}.json").read_text())
        self.assertEqual(stored, finished)
        self.assertEqual(finished["outcome"], "done")
        self.assertEqual(finished["after"], {str(self.skill_file): "after text"})
        self.assertEqual(finished["note"], "Added a call in step 2.")
        self.assertFalse((self.paths.active / f"{task['id']}.json").exists())

    def test_declined_task_can_be_filed_straight_from_the_inbox(self):
        task = self.link()
        self.assertEqual(done(self.paths, task["id"], "declined", "Not now.")["outcome"], "declined")
        self.assertEqual(pending(self.paths), [])

    def test_unknown_outcome_is_refused(self):
        task = self.link()
        with self.assertRaises(TaskError):
            done(self.paths, task["id"], "maybe", "")

    def test_unknown_task_is_refused(self):
        with self.assertRaises(TaskError):
            start(self.paths, "nope", self.skills)

    def test_task_ids_cannot_reach_outside_the_folders(self):
        with self.assertRaises(TaskError):
            start(self.paths, "../../etc/passwd", self.skills)

    def test_in_flight_holds_waiting_and_active(self):
        waiting, active = self.link(), self.link()
        start(self.paths, active["id"], self.skills)
        self.assertEqual({t["id"]: t["state"] for t in in_flight(self.paths)},
                         {waiting["id"]: "waiting", active["id"]: "active"})

    def test_new_since_reports_each_waiting_task_once(self):
        seen = set()
        first = self.link()
        self.assertEqual([t["id"] for t in new_since(self.paths, seen)], [first["id"]])
        self.assertEqual(new_since(self.paths, seen), [])
        second = self.link()
        self.assertEqual([t["id"] for t in new_since(self.paths, seen)], [second["id"]])


if __name__ == "__main__":
    unittest.main()
