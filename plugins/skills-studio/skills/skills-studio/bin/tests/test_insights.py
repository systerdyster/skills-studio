"""Analyse's findings — judgements the local checks cannot make — are kept with a fingerprint of
every skill they concern. A finding lives only while all those texts are unchanged, so a fixed
problem never lingers; Analyse replaces the whole set each time it runs."""

import tempfile
import unittest
from pathlib import Path

from sx import insights
from sx.insights import InsightsError, as_findings, live, save
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

    def test_an_unreadable_file_reads_as_none(self):
        self.paths.ensure()
        self.paths.insights.write_text("{not json")
        self.assertEqual(insights.read(self.paths), [])


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


if __name__ == "__main__":
    unittest.main()
