"""Each local check, firing and not firing. Checks need no model: they read the scan and the wires."""

import hashlib
import unittest

from sx.checks import DESCRIPTION_MAX, DESCRIPTION_MIN, checks, content_hash

GOOD = "Close a finished case: merge, verify, move the tracker. Use when the case is done."


def s(name, description=GOOD, body="", source="project", error=None, metadata=None, **extra):
    frontmatter = None if error == "missing frontmatter" else {"name": name, "description": description}
    if frontmatter is not None and metadata is not None:
        frontmatter["metadata"] = metadata
    if error and error != "missing frontmatter":
        frontmatter = None
    skill = {"id": name, "name": name, "source": source, "body": body, "frontmatter": frontmatter,
             "error": error, "body_line": 1}
    skill.update(extra)
    return skill


def found(skills, wires=(), sources=None):
    """Every finding but trigger overlap: the fixtures share one description on purpose."""
    return {(f["skill"], f["check"]) for f in checks(skills, list(wires), sources or {})
            if f["check"] != "trigger-overlap"}


def only(skills, check, wires=(), sources=None):
    return [f for f in checks(skills, list(wires), sources or {}) if f["check"] == check]


class CleanTest(unittest.TestCase):
    def test_a_clean_skill_has_no_findings(self):
        self.assertEqual(found([s("close-feature")]), set())


class FrontmatterTest(unittest.TestCase):
    def test_missing_frontmatter(self):
        self.assertIn(("bare", "frontmatter-missing"), found([s("bare", error="missing frontmatter")]))

    def test_broken_frontmatter_carries_the_reader_message(self):
        result = only([s("broken", error="line 2: expected 'key: value'")], "frontmatter-broken")
        self.assertEqual(result[0]["level"], "error")
        self.assertIn("line 2", result[0]["message"])

    def test_missing_name(self):
        skill = s("x")
        del skill["frontmatter"]["name"]
        self.assertIn(("x", "name-missing"), found([skill]))

    def test_missing_description(self):
        skill = s("x")
        skill["frontmatter"]["description"] = "  "
        self.assertIn(("x", "description-missing"), found([skill]))
        self.assertNotIn(("x", "description-short"), found([skill]))


class DescriptionLengthTest(unittest.TestCase):
    def test_too_long(self):
        self.assertIn(("x", "description-long"), found([s("x", "a" * (DESCRIPTION_MAX + 1))]))

    def test_at_the_limit_is_fine(self):
        self.assertEqual(found([s("x", "a" * DESCRIPTION_MAX)]), set())

    def test_too_short(self):
        self.assertIn(("x", "description-short"), found([s("x", "Merges.")]))

    def test_at_the_minimum_is_fine(self):
        self.assertEqual(found([s("x", "a" * DESCRIPTION_MIN)]), set())


class BrokenWireTest(unittest.TestCase):
    def test_broken_wire_is_reported_on_the_skill_that_names_it(self):
        wire = {"from": "close-feature", "to": "git-finish", "order": 1, "line": 7, "broken": True}
        result = only([s("close-feature")], "wire-broken", [wire])
        self.assertEqual(result[0]["skill"], "close-feature")
        self.assertEqual(result[0]["line"], 7)
        self.assertIn("git-finish", result[0]["message"])

    def test_working_wire_is_not_reported(self):
        wire = {"from": "a", "to": "b", "order": 1, "line": 1, "broken": False}
        self.assertEqual(found([s("a"), s("b")], [wire]), set())


class DuplicateTest(unittest.TestCase):
    def test_same_name_in_project_and_user_shadows(self):
        result = found([s("commit"), s("commit", source="user")])
        self.assertIn(("commit", "name-duplicate"), result)

    def test_same_bare_name_in_a_plugin_is_not_a_duplicate(self):
        plugin_skill = s("commit", source="plugin", plugin="git")
        plugin_skill["id"] = "git:commit"
        self.assertEqual(found([s("commit"), plugin_skill]), set())


class OverlapTest(unittest.TestCase):
    def test_near_identical_triggers_overlap(self):
        a = s("close-feature", "Close a finished case: merge the branch, verify, move the tracker ticket.")
        b = s("finish-case", "Finish a case: merge the branch, verify it, move the tracker ticket to done.")
        result = only([a, b], "trigger-overlap")
        self.assertEqual({f["skill"] for f in result}, {"close-feature", "finish-case"})
        self.assertEqual(result[0]["level"], "info")

    def test_different_triggers_do_not_overlap(self):
        a = s("close-feature", "Close a finished case: merge the branch, verify, move the tracker ticket.")
        b = s("grill-me", "Stress-test a design by asking one sharp question at a time until it holds.")
        self.assertEqual(only([a, b], "trigger-overlap"), [])


class CopyTest(unittest.TestCase):
    def test_a_path_into_the_home_folder_in_a_copy_is_personal(self):
        for body in ("Read ~/notes/rules.md first.", "See /Users/someone/notes.", "See /home/someone/notes."):
            copy = s("tdd-team", body=body, metadata={"copied_from": "my-tdd", "copied_hash": "x"})
            self.assertIn(("tdd-team", "copy-personal"), found([copy]), body)

    def test_a_path_inside_the_project_is_not_personal(self):
        copy = s("tdd-team", body="See ./docs/rules.md and PROJECT-RULES.md.",
                 metadata={"copied_from": "my-tdd", "copied_hash": "x"})
        self.assertNotIn(("tdd-team", "copy-personal"), found([copy]))

    def test_personal_content_outside_a_copy_is_not_flagged(self):
        self.assertEqual(found([s("own", body="Read ~/notes/rules.md first.")]), set())

    def test_source_changed_since_copy(self):
        copy = s("tdd-team", metadata={"copied_from": "my-tdd", "copied_hash": content_hash("old")})
        source = s("my-tdd", source="user")
        result = found([copy, source], sources={"my-tdd": "new text"})
        self.assertIn(("tdd-team", "copy-source-changed"), result)

    def test_source_unchanged_since_copy(self):
        copy = s("tdd-team", metadata={"copied_from": "my-tdd", "copied_hash": content_hash("same")})
        result = found([copy, s("my-tdd", source="user")], sources={"my-tdd": "same"})
        self.assertEqual(result, set())

    def test_source_gone(self):
        copy = s("tdd-team", metadata={"copied_from": "my-tdd", "copied_hash": "x"})
        self.assertIn(("tdd-team", "copy-source-gone"), found([copy]))

    def test_content_hash_is_short_sha256(self):
        self.assertEqual(content_hash("abc"), hashlib.sha256(b"abc").hexdigest()[:12])


if __name__ == "__main__":
    unittest.main()
