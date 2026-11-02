"""Analyse's findings — judgements the local checks cannot make — are kept with a fingerprint of
every skill they concern. A finding lives only while all those texts are unchanged, so a fixed
problem never lingers; Analyse replaces the whole set each time it runs."""

import tempfile
import unittest
from pathlib import Path

from sx import insights
from sx.insights import InsightsError, as_findings, dismiss, dismissals, live, partition, restore, save
from sx.state import StudioPaths
from sx.wirekinds import fingerprint

TEXTS = {"code-review": "review text", "commit": "commit text", "my-tdd": "tdd text"}
SKILLS = [
    {"id": "code-review", "source": "project"},
    {"id": "commit", "source": "project"},
    {"id": "my-tdd", "source": "user"},
]
DISAGREE = {
    "kind": "disagreement",
    "skills": ["code-review", "commit"],
    "message": "code-review says commit runs it first; commit only lists it under Related.",
    "lines": {"code-review": [335], "commit": [76]},
}
SPLIT = {
    "kind": "split",
    "skills": ["code-review"],
    "message": "The security pass is a skill of its own, spread over steps 3 and 6.",
    "lines": {"code-review": [40, 88]},
    "proposal": {"skill": "code-review", "text": "Split the security pass into security-review; call it at steps 3 and 6."},
}


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = StudioPaths(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_saved_with_the_fingerprint_of_each_skill(self):
        save(self.paths, [DISAGREE], SKILLS, TEXTS)
        [kept] = insights.read(self.paths)
        self.assertEqual(kept["fingerprints"], {"code-review": fingerprint("review text"), "commit": fingerprint("commit text")})

    def test_a_new_run_replaces_the_set(self):
        save(self.paths, [DISAGREE], SKILLS, TEXTS)
        save(self.paths, [], SKILLS, TEXTS)
        self.assertEqual(insights.read(self.paths), [])

    def test_only_known_kinds(self):
        with self.assertRaisesRegex(InsightsError, "kind"):
            save(self.paths, [{**DISAGREE, "kind": "vibes"}], SKILLS, TEXTS)

    def test_only_skills_in_scope(self):
        with self.assertRaisesRegex(InsightsError, "no skill"):
            save(self.paths, [{**DISAGREE, "skills": ["code-review", "gone"]}], SKILLS, TEXTS)

    def test_at_least_one_project_skill(self):
        with self.assertRaisesRegex(InsightsError, "project"):
            save(self.paths, [{**DISAGREE, "skills": ["my-tdd"], "lines": {}}], SKILLS, TEXTS)

    def test_a_message_is_needed(self):
        with self.assertRaisesRegex(InsightsError, "message"):
            save(self.paths, [{**DISAGREE, "message": " "}], SKILLS, TEXTS)

    def test_a_suggestion_keeps_the_change_it_would_send(self):
        save(self.paths, [SPLIT], SKILLS, TEXTS)
        [kept] = insights.read(self.paths)
        self.assertEqual(kept["proposal"], SPLIT["proposal"])

    def test_a_suggestion_needs_a_proposal(self):
        with self.assertRaisesRegex(InsightsError, "proposal"):
            save(self.paths, [{k: v for k, v in SPLIT.items() if k != "proposal"}], SKILLS, TEXTS)

    def test_a_proposal_changes_a_project_skill_it_concerns(self):
        for skill in ("commit", "my-tdd"):
            with self.subTest(skill=skill), self.assertRaisesRegex(InsightsError, "proposal"):
                save(self.paths, [{**SPLIT, "skills": ["code-review", "my-tdd"],
                                   "proposal": {"skill": skill, "text": "Split it."}}], SKILLS, TEXTS)

    def test_a_proposal_says_what_to_do(self):
        with self.assertRaisesRegex(InsightsError, "proposal"):
            save(self.paths, [{**SPLIT, "proposal": {"skill": "code-review", "text": " "}}], SKILLS, TEXTS)

    def test_a_finding_may_carry_a_proposal_too(self):
        save(self.paths, [{**DISAGREE, "proposal": {"skill": "commit", "text": "Say code-review runs first."}}], SKILLS, TEXTS)
        [kept] = insights.read(self.paths)
        self.assertEqual(kept["proposal"]["skill"], "commit")

    def test_a_finding_without_a_proposal_has_none(self):
        save(self.paths, [DISAGREE], SKILLS, TEXTS)
        [kept] = insights.read(self.paths)
        self.assertNotIn("proposal", kept)

    def test_an_unreadable_file_reads_as_none(self):
        self.paths.ensure()
        self.paths.insights.write_text("{not json")
        self.assertEqual(insights.read(self.paths), [])


class DismissTest(unittest.TestCase):
    """A dismissed item stays hidden while its texts are unchanged — also when Analyse makes it again,
    in other words — and comes back to be judged anew once any of them changes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = StudioPaths(Path(self.tmp.name))
        save(self.paths, [DISAGREE, SPLIT], SKILLS, TEXTS)

    def tearDown(self):
        self.tmp.cleanup()

    def shown_and_dismissed(self, texts=TEXTS):
        shown, dismissed = partition(live(insights.read(self.paths), texts), dismissals(self.paths))
        return [i["kind"] for i in shown], [i["kind"] for i in dismissed]

    def test_a_dismissed_item_is_set_apart(self):
        dismiss(self.paths, {"kind": "split", "skills": ["code-review"]}, TEXTS)
        self.assertEqual(self.shown_and_dismissed(), (["disagreement"], ["split"]))

    def test_the_skills_match_in_any_order(self):
        dismiss(self.paths, {"kind": "disagreement", "skills": ["commit", "code-review"]}, TEXTS)
        self.assertEqual(self.shown_and_dismissed(), (["split"], ["disagreement"]))

    def test_it_stays_dismissed_when_analyse_says_it_again(self):
        dismiss(self.paths, {"kind": "split", "skills": ["code-review"]}, TEXTS)
        save(self.paths, [{**SPLIT, "message": "Same split, other words."}], SKILLS, TEXTS)
        self.assertEqual(self.shown_and_dismissed(), ([], ["split"]))

    def test_it_comes_back_once_the_text_changes(self):
        dismiss(self.paths, {"kind": "split", "skills": ["code-review"]}, TEXTS)
        changed = {**TEXTS, "code-review": "review text, rewritten"}
        save(self.paths, [SPLIT], SKILLS, changed)
        self.assertEqual(self.shown_and_dismissed(changed), (["split"], []))

    def test_a_lapsed_dismissal_is_dropped_on_the_next_write(self):
        dismiss(self.paths, {"kind": "split", "skills": ["code-review"]}, TEXTS)
        changed = {**TEXTS, "code-review": "review text, rewritten"}
        save(self.paths, [{"kind": "unused", "skills": ["commit"], "message": "Nobody says commit."}], SKILLS, changed)
        dismiss(self.paths, {"kind": "unused", "skills": ["commit"]}, changed)
        self.assertEqual([d["kind"] for d in dismissals(self.paths)], ["unused"])

    def test_restore_brings_it_back(self):
        dismiss(self.paths, {"kind": "split", "skills": ["code-review"]}, TEXTS)
        restore(self.paths, {"kind": "split", "skills": ["code-review"]})
        self.assertEqual(self.shown_and_dismissed(), (["disagreement", "split"], []))

    def test_only_an_item_that_holds_can_be_dismissed(self):
        with self.assertRaisesRegex(InsightsError, "no such"):
            dismiss(self.paths, {"kind": "merge", "skills": ["code-review"]}, TEXTS)

    def test_a_dismissal_names_kind_and_skills(self):
        with self.assertRaisesRegex(InsightsError, "kind"):
            dismiss(self.paths, {"skills": ["code-review"]}, TEXTS)

    def test_an_unreadable_file_dismisses_nothing(self):
        self.paths.dismissed.write_text("{not json")
        self.assertEqual(dismissals(self.paths), [])


class LiveTest(unittest.TestCase):
    def kept(self):
        return {**DISAGREE, "fingerprints": {s: fingerprint(TEXTS[s]) for s in DISAGREE["skills"]}}

    def test_live_while_every_text_is_unchanged(self):
        self.assertEqual(len(live([self.kept()], TEXTS)), 1)

    def test_gone_once_either_text_changes(self):
        self.assertEqual(live([self.kept()], {**TEXTS, "commit": "commit text, fixed"}), [])

    def test_each_skill_gets_the_finding_with_its_own_line_and_the_other(self):
        found = {f["skill"]: f for f in as_findings(live([self.kept()], TEXTS))}
        self.assertEqual(found["code-review"]["line"], 335)
        self.assertEqual(found["commit"]["other"], "code-review")
        self.assertEqual(found["commit"]["check"], "analyse-disagreement")
        self.assertEqual(found["commit"]["level"], "warning")

    def test_a_suggestion_shows_on_its_skill_as_info(self):
        kept = {**SPLIT, "fingerprints": {"code-review": fingerprint(TEXTS["code-review"])}}
        [found] = as_findings(live([kept], TEXTS))
        self.assertEqual((found["check"], found["level"]), ("analyse-split", "info"))


if __name__ == "__main__":
    unittest.main()
