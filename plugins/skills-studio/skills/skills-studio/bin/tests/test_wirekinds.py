"""Whether a wire is a call or a mention is Claude's judgement, made in an Analyse task and kept per
skill with a fingerprint of its text: a skill whose text has changed is judged again, and until it
is, its wires carry no kind."""

import tempfile
import unittest
from pathlib import Path

from sx import wirekinds
from sx.state import StudioPaths
from sx.wirekinds import KindsError, apply, fingerprint, pending, save

TEXTS = {
    "commit": "---\nname: commit\n---\nSee `code-review`.\n",
    "tdd": "---\nname: tdd\n---\nThen use `commit`.\n",
    "my-tdd": "---\nname: my-tdd\n---\nUse `commit`.\n",
}
SKILLS = [
    {"id": "commit", "source": "project", "path": "commit/SKILL.md"},
    {"id": "tdd", "source": "project", "path": "tdd/SKILL.md"},
    {"id": "code-review", "source": "project", "path": "code-review/SKILL.md"},
    {"id": "my-tdd", "source": "user", "path": "my-tdd/SKILL.md"},
]
WIRES = [
    {"from": "commit", "to": "code-review", "lines": [4], "broken": False},
    {"from": "tdd", "to": "commit", "lines": [4], "broken": False},
    {"from": "my-tdd", "to": "commit", "lines": [4], "broken": False},
    {"from": "tdd", "to": "gone", "lines": [4], "broken": True},
]


def judged(skill, **kinds):
    return {"fingerprint": fingerprint(TEXTS[skill]),
            "wires": {to: {"kind": kind, "reason": "because"} for to, kind in kinds.items()}}


class PendingTest(unittest.TestCase):
    def test_every_project_skill_with_wires_is_pending_at_first(self):
        found = pending(SKILLS, WIRES, TEXTS, {})
        self.assertEqual([p["skill"] for p in found], ["commit", "tdd"])
        self.assertEqual(found[1]["wires"], [{"to": "commit", "lines": [{"line": 4, "text": "Then use `commit`."}]}])

    def test_a_judged_skill_is_not_pending_until_its_text_changes(self):
        saved = {"commit": judged("commit", **{"code-review": "mention"}), "tdd": judged("tdd", commit="call")}
        self.assertEqual(pending(SKILLS, WIRES, TEXTS, saved), [])
        changed = {**TEXTS, "tdd": TEXTS["tdd"] + "More.\n"}
        self.assertEqual([p["skill"] for p in pending(SKILLS, WIRES, changed, saved)], ["tdd"])


class ApplyTest(unittest.TestCase):
    def test_wires_get_the_kind_while_the_text_is_unchanged(self):
        saved = {"commit": judged("commit", **{"code-review": "mention"})}
        result = {(w["from"], w["to"]): w for w in apply(WIRES, TEXTS, saved)}
        self.assertEqual(result[("commit", "code-review")]["kind"], "mention")
        self.assertEqual(result[("commit", "code-review")]["reason"], "because")
        self.assertIsNone(result[("tdd", "commit")]["kind"])

    def test_a_changed_text_drops_the_kind(self):
        saved = {"commit": judged("commit", **{"code-review": "mention"})}
        changed = {**TEXTS, "commit": TEXTS["commit"] + "x"}
        self.assertIsNone(apply(WIRES, changed, saved)[0]["kind"])


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = StudioPaths(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_saved_kinds_are_read_back_and_merged(self):
        save(self.paths, {"commit": judged("commit", **{"code-review": "mention"})}, SKILLS, WIRES, TEXTS)
        save(self.paths, {"tdd": judged("tdd", commit="call")}, SKILLS, WIRES, TEXTS)
        self.assertEqual(set(wirekinds.read(self.paths)), {"commit", "tdd"})

    def test_a_judgement_on_old_text_is_refused(self):
        stale = {"tdd": {**judged("tdd", commit="call"), "fingerprint": "old"}}
        with self.assertRaisesRegex(KindsError, "changed"):
            save(self.paths, stale, SKILLS, WIRES, TEXTS)

    def test_only_call_or_mention(self):
        with self.assertRaisesRegex(KindsError, "call or mention"):
            save(self.paths, {"tdd": judged("tdd", commit="maybe")}, SKILLS, WIRES, TEXTS)

    def test_only_wires_the_skill_has(self):
        with self.assertRaisesRegex(KindsError, "no wire"):
            save(self.paths, {"tdd": judged("tdd", **{"code-review": "call"})}, SKILLS, WIRES, TEXTS)

    def test_every_wire_of_the_skill_is_judged(self):
        with self.assertRaisesRegex(KindsError, "not judged"):
            save(self.paths, {"tdd": {"fingerprint": fingerprint(TEXTS["tdd"]), "wires": {}}}, SKILLS, WIRES, TEXTS)

    def test_only_project_skills(self):
        with self.assertRaisesRegex(KindsError, "project"):
            save(self.paths, {"my-tdd": judged("my-tdd", commit="call")}, SKILLS, WIRES, TEXTS)

    def test_an_unreadable_file_reads_as_nothing_judged(self):
        self.paths.ensure()
        self.paths.wire_kinds.write_text("{not json")
        self.assertEqual(wirekinds.read(self.paths), {})


if __name__ == "__main__":
    unittest.main()
