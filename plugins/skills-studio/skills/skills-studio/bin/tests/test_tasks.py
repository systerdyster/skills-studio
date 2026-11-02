"""A task is what the canvas asks the session to do. It is checked before it reaches inbox/: only
project skills may be changed, and a new name must be free."""

import json
import tempfile
import unittest
from pathlib import Path

from sx.state import StudioPaths
from sx.tasks import TaskError, submit, validate


def sk(name, source="project", plugin=None):
    skill = {"id": f"{plugin}:{name}" if plugin else name, "name": name, "source": source,
             "writable": source == "project"}
    if plugin:
        skill["plugin"] = plugin
    return skill


SKILLS = [sk("close-feature"), sk("git-finish"), sk("brain-tdd", "user"),
          sk("triage-issue", "plugin", "atlassian")]


class ValidateTest(unittest.TestCase):
    def test_link_from_a_project_skill(self):
        task = validate({"kind": "link", "from": "close-feature", "to": "git-finish"}, SKILLS)
        self.assertEqual(task["kind"], "link")

    def test_link_to_a_read_only_skill_is_allowed(self):
        validate({"kind": "link", "from": "close-feature", "to": "atlassian:triage-issue"}, SKILLS)

    def test_link_from_a_user_skill_is_refused(self):
        with self.assertRaisesRegex(TaskError, "read-only"):
            validate({"kind": "link", "from": "brain-tdd", "to": "git-finish"}, SKILLS)

    def test_link_to_an_unknown_skill_is_refused(self):
        with self.assertRaisesRegex(TaskError, "no skill"):
            validate({"kind": "link", "from": "close-feature", "to": "nope"}, SKILLS)

    def test_edit_description_of_a_project_skill(self):
        task = validate({"kind": "edit", "skill": "git-finish", "field": "description", "value": "Merge it."}, SKILLS)
        self.assertEqual(task["value"], "Merge it.")

    def test_edit_of_a_plugin_skill_is_refused(self):
        with self.assertRaisesRegex(TaskError, "read-only"):
            validate({"kind": "edit", "skill": "atlassian:triage-issue", "field": "description", "value": "x"}, SKILLS)

    def test_edit_of_another_field_is_refused(self):
        with self.assertRaisesRegex(TaskError, "field"):
            validate({"kind": "edit", "skill": "git-finish", "field": "license", "value": "x"}, SKILLS)

    def test_improve_a_project_skill_with_or_without_a_focus(self):
        self.assertEqual(validate({"kind": "improve", "skill": "git-finish", "focus": ""}, SKILLS)["focus"], "")
        validate({"kind": "improve", "skill": "git-finish", "focus": "Make the description trigger."}, SKILLS)

    def test_improve_of_a_user_skill_is_refused(self):
        with self.assertRaisesRegex(TaskError, "read-only"):
            validate({"kind": "improve", "skill": "brain-tdd", "focus": ""}, SKILLS)

    def test_delete_only_a_project_skill(self):
        validate({"kind": "delete", "skill": "git-finish"}, SKILLS)
        with self.assertRaisesRegex(TaskError, "read-only"):
            validate({"kind": "delete", "skill": "atlassian:triage-issue"}, SKILLS)

    def test_change_in_words(self):
        validate({"kind": "change", "skill": "close-feature", "text": "Extract the git handling."}, SKILLS)

    def test_new_skill_needs_a_free_kebab_name(self):
        validate({"kind": "new", "name": "wiki-sync", "description": "Sync the wiki.", "intent": ""}, SKILLS)
        with self.assertRaisesRegex(TaskError, "taken"):
            validate({"kind": "new", "name": "git-finish", "description": "x", "intent": ""}, SKILLS)
        with self.assertRaisesRegex(TaskError, "name"):
            validate({"kind": "new", "name": "Git Finish", "description": "x", "intent": ""}, SKILLS)

    def test_copy_needs_a_new_name(self):
        validate({"kind": "copy", "source": "brain-tdd", "name": "tdd-team"}, SKILLS)
        with self.assertRaisesRegex(TaskError, "taken"):
            validate({"kind": "copy", "source": "brain-tdd", "name": "brain-tdd"}, SKILLS)

    def test_copy_of_an_unknown_skill_is_refused(self):
        with self.assertRaisesRegex(TaskError, "no skill"):
            validate({"kind": "copy", "source": "nope", "name": "x-y"}, SKILLS)

    def test_analyse_takes_nothing(self):
        self.assertEqual(validate({"kind": "analyse"}, SKILLS)["kind"], "analyse")

    def test_unknown_kind_is_refused(self):
        with self.assertRaisesRegex(TaskError, "kind"):
            validate({"kind": "rewrite", "skill": "git-finish"}, SKILLS)

    def test_missing_field_is_refused(self):
        with self.assertRaisesRegex(TaskError, "to"):
            validate({"kind": "link", "from": "close-feature"}, SKILLS)

    def test_extra_fields_are_dropped_and_text_is_capped(self):
        task = validate({"kind": "change", "skill": "close-feature", "text": "x" * 10000, "evil": 1}, SKILLS)
        self.assertNotIn("evil", task)
        self.assertEqual(len(task["text"]), 4000)


class SubmitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = StudioPaths(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_submitted_task_lands_in_inbox_as_one_json_file(self):
        task = submit(self.paths, {"kind": "analyse"}, SKILLS)
        files = list(self.paths.inbox.iterdir())
        self.assertEqual([f.name for f in files], [f"{task['id']}.json"])
        stored = json.loads(files[0].read_text())
        self.assertEqual(stored["kind"], "analyse")
        self.assertRegex(stored["created_at"], r"^\d{4}-\d\d-\d\dT")

    def test_task_ids_sort_in_the_order_they_were_made(self):
        first = submit(self.paths, {"kind": "analyse"}, SKILLS)["id"]
        second = submit(self.paths, {"kind": "analyse"}, SKILLS)["id"]
        self.assertLess(first, second)

    def test_refused_task_writes_nothing(self):
        with self.assertRaises(TaskError):
            submit(self.paths, {"kind": "delete"}, SKILLS)
        self.assertFalse(self.paths.inbox.exists() and any(self.paths.inbox.iterdir()))


if __name__ == "__main__":
    unittest.main()
