"""A flow starts where nothing outside it calls in — a project skill nobody calls, or a loop of them —
and holds everything it reaches. Flows may share skills; only project skills are followed further."""

import unittest

from sx.flows import flows


def s(name, source="project"):
    return {"id": name, "name": name, "source": source}


def w(source, target, broken=False):
    return {"from": source, "to": target, "broken": broken}


def by_entry(skills, wires):
    return {tuple(f["entry"]): f["skills"] for f in flows(skills, wires)}


class FlowTest(unittest.TestCase):
    def test_an_uncalled_skill_starts_a_flow_with_all_it_reaches(self):
        result = by_entry([s("a"), s("b"), s("c")], [w("a", "b"), w("b", "c")])
        self.assertEqual(result, {("a",): ["a", "b", "c"]})

    def test_a_loop_nobody_else_calls_is_one_entry(self):
        result = by_entry([s("release"), s("hotfix"), s("notes")],
                          [w("release", "hotfix"), w("hotfix", "release"), w("hotfix", "notes")])
        self.assertEqual(result, {("hotfix", "release"): ["hotfix", "notes", "release"]})

    def test_flows_may_share_skills(self):
        result = by_entry([s("a"), s("b"), s("shared")], [w("a", "shared"), w("b", "shared")])
        self.assertEqual(result, {("a",): ["a", "shared"], ("b",): ["b", "shared"]})

    def test_a_loop_called_from_outside_is_not_an_entry(self):
        result = by_entry([s("a"), s("x"), s("y")], [w("a", "x"), w("x", "y"), w("y", "x")])
        self.assertEqual(result, {("a",): ["a", "x", "y"]})

    def test_a_skill_with_no_wires_is_its_own_flow(self):
        self.assertEqual(by_entry([s("alone")], []), {("alone",): ["alone"]})

    def test_other_sources_are_leaves_not_entries(self):
        result = by_entry([s("a"), s("tdd", "user"), s("b")],
                          [w("a", "tdd"), w("tdd", "b")])
        self.assertEqual(result, {("a",): ["a", "tdd"], ("b",): ["b"]})

    def test_broken_wires_are_left_out(self):
        self.assertEqual(by_entry([s("a")], [w("a", "gone", broken=True)]), {("a",): ["a"]})

    def test_flows_are_ordered_by_entry(self):
        entries = [f["entry"] for f in flows([s("b"), s("a")], [])]
        self.assertEqual(entries, [["a"], ["b"]])


if __name__ == "__main__":
    unittest.main()
