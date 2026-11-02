"""A wire A → B is every mention of B in A's body by the name Claude knows it by; the text is the
only truth. Plugin and synced skills count only by their qualified name (`atlassian:triage-issue`),
one-word project and user skills only when written as a skill (`commit`, /commit). A skill-looking
reference to a name that is not in scope is a broken wire."""

import unittest

from sx.wires import wires


def s(name, body="", source="project", plugin=None):
    skill = {"name": name, "body": body, "source": source}
    if plugin:
        skill["plugin"] = plugin
    return skill


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


class QualifiedNameTest(unittest.TestCase):
    def test_plugin_skill_counts_by_its_qualified_name(self):
        triage = s("triage-issue", source="plugin", plugin="atlassian")
        result = found([s("a", "Use atlassian:triage-issue first."), triage])
        self.assertIn(("a", "atlassian:triage-issue"), result)

    def test_plugin_skill_by_its_bare_name_is_not_a_wire(self):
        triage = s("triage-issue", source="plugin", plugin="atlassian")
        self.assertEqual(found([s("a", "We triage-issue reports weekly."), triage]), {})

    def test_synced_skill_counts_as_anthropic_skills(self):
        docs = s("docs", source="synced")
        result = found([s("a", "Make it with anthropic-skills:docs."), docs])
        self.assertIn(("a", "anthropic-skills:docs"), result)

    def test_plain_word_matching_a_synced_skill_is_not_a_wire(self):
        docs = s("docs", source="synced")
        self.assertEqual(found([s("a", "Search company docs and internal docs."), docs]), {})

    def test_skills_of_one_plugin_reach_each_other_by_bare_name(self):
        triage = s("triage-issue", "Hand over to spec-to-backlog.", source="plugin", plugin="atlassian")
        spec = s("spec-to-backlog", source="plugin", plugin="atlassian")
        self.assertIn(("atlassian:triage-issue", "atlassian:spec-to-backlog"), found([triage, spec]))

    def test_bare_name_of_another_plugins_skill_is_not_a_wire(self):
        mine = s("mine", "Hand over to spec-to-backlog.", source="plugin", plugin="other")
        spec = s("spec-to-backlog", source="plugin", plugin="atlassian")
        self.assertEqual(found([mine, spec]), {})

    def test_wire_from_a_plugin_skill_names_it_qualified(self):
        source = s("factory", "Then run brain-review-security.", source="plugin", plugin="factory")
        self.assertIn(("factory:factory", "brain-review-security"),
                      found([source, s("brain-review-security", source="user")]))

    def test_a_project_skill_is_not_matched_inside_a_qualified_name(self):
        result = found([
            s("a", "Use atlassian:triage-issue."),
            s("triage-issue"),
            s("triage-issue", source="plugin", plugin="atlassian"),
        ])
        self.assertEqual(set(result), {("a", "atlassian:triage-issue")})


class OneWordNameTest(unittest.TestCase):
    def test_one_word_name_as_plain_word_is_not_a_wire(self):
        self.assertEqual(found([s("a", "Commit the change, then tdd it."), s("commit"), s("tdd")]), {})

    def test_one_word_name_in_backticks_is_a_wire(self):
        self.assertIn(("a", "commit"), found([s("a", "Then run `commit`."), s("commit")]))

    def test_one_word_name_as_slash_command_is_a_wire(self):
        self.assertIn(("a", "commit"), found([s("a", "Then type /commit."), s("commit")]))

    def test_one_word_name_inside_a_path_is_not_a_wire(self):
        self.assertEqual(found([s("a", "See src/commit/index.ts"), s("commit")]), {})

    def test_self_mention_is_ignored(self):
        self.assertEqual(found([s("brain-tdd", "brain-tdd drives red, green, blue.")]), {})

    def test_mentions_in_the_frontmatter_do_not_count(self):
        skill = {"name": "child", "body": "", "frontmatter": {"description": "see parent"}}
        self.assertEqual(found([skill, s("parent")]), {})

    def test_several_mentions_make_one_wire(self):
        self.assertEqual(len(wires([s("a", "git-finish, then git-finish again"), s("git-finish")])), 1)


class OrderTest(unittest.TestCase):
    def test_wires_are_numbered_by_first_mention(self):
        body = "First grill-me. Then `tdd`. Then grill-me again, and finally git-finish."
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
