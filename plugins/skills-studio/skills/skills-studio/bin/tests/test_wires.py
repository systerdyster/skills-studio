"""A wire A → B is every whole-word mention of B's name in A's body; the text is the only truth.
A skill-looking reference to a name that is not in scope is a broken wire."""

import unittest

from sx.wires import wires


def s(name, body=""):
    return {"name": name, "body": body}


def found(skills):
    return {(w["from"], w["to"]): w for w in wires(skills)}


class WireTest(unittest.TestCase):
    def test_plain_call_is_a_wire(self):
        result = found([s("close-feature", "Then run `git-finish`."), s("git-finish")])
        self.assertIn(("close-feature", "git-finish"), result)
        self.assertFalse(result[("close-feature", "git-finish")]["broken"])

    def test_awkward_mention_is_still_a_wire(self):
        body = "This is not the same as brain-code-review; do not run it here."
        self.assertIn(("close-feature", "brain-code-review"),
                      found([s("close-feature", body), s("brain-code-review")]))

    def test_a_name_inside_a_longer_name_is_not_a_mention(self):
        result = found([
            s("brain-code-review", "Run brain-review-security."),
            s("brain-review"),
            s("brain-review-security"),
        ])
        self.assertIn(("brain-code-review", "brain-review-security"), result)
        self.assertNotIn(("brain-code-review", "brain-review"), result)

    def test_plugin_prefixed_mention_counts(self):
        self.assertIn(("a", "triage-issue"),
                      found([s("a", "Use atlassian:triage-issue first."), s("triage-issue")]))

    def test_self_mention_is_ignored(self):
        self.assertEqual(found([s("brain-tdd", "brain-tdd drives red, green, blue.")]), {})

    def test_mentions_in_the_frontmatter_do_not_count(self):
        skill = {"name": "child", "body": "", "frontmatter": {"description": "see parent"}}
        self.assertEqual(found([skill, s("parent")]), {})

    def test_several_mentions_make_one_wire(self):
        self.assertEqual(len(wires([s("a", "b, then b again, then b"), s("b")])), 1)


class OrderTest(unittest.TestCase):
    def test_wires_are_numbered_by_first_mention(self):
        body = "First grill-me. Then tdd. Then grill-me again, and finally git-finish."
        result = found([s("flow", body), s("tdd"), s("git-finish"), s("grill-me")])
        self.assertEqual(result[("flow", "grill-me")]["order"], 1)
        self.assertEqual(result[("flow", "tdd")]["order"], 2)
        self.assertEqual(result[("flow", "git-finish")]["order"], 3)

    def test_each_mention_line_is_kept_for_the_view(self):
        body = "intro\nThen run `git-finish` here.\n"
        wire = found([s("a", body), s("git-finish")])[("a", "git-finish")]
        self.assertEqual(wire["line"], 2)

    def test_line_counts_from_the_top_of_the_file(self):
        skill = {"name": "a", "body": "intro\nrun git-finish\n", "body_line": 5}
        self.assertEqual(found([skill, s("git-finish")])[("a", "git-finish")]["line"], 6)


class BrokenTest(unittest.TestCase):
    def test_missing_skill_named_as_a_skill_is_broken(self):
        result = found([s("close-feature", "Run the `git-finish` skill.")])
        self.assertTrue(result[("close-feature", "git-finish")]["broken"])

    def test_missing_slash_command_is_broken(self):
        result = found([s("close-feature", "Then type /git-finish to merge.")])
        self.assertTrue(result[("close-feature", "git-finish")]["broken"])

    def test_code_and_flags_are_not_skill_references(self):
        body = "Run `git merge --no-ff` and check `src/app-main.ts` and the `build-output` folder."
        self.assertEqual(found([s("close-feature", body)]), {})

    def test_paths_are_not_slash_commands(self):
        self.assertEqual(found([s("a", "Read ~/.claude/skills/some-thing/SKILL.md")]), {})

    def test_broken_wire_is_one_per_name(self):
        body = "Use the `git-finish` skill. Later, the `git-finish` skill again."
        self.assertEqual(len(wires([s("a", body)])), 1)


if __name__ == "__main__":
    unittest.main()
