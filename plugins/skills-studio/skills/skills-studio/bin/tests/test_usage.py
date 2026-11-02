"""Usage comes from Claude Code's /skill-doctor report, which is text only: rows are read by their
columns, matched to the scan by id or, for project and user skills, by folder, and anything that
does not look like a row is skipped rather than guessed at."""

import threading
import unittest

from sx.usage import Usage, match, parse

REPORT = """Skills loaded this session

  skill                                       source           context  7d tokens   uses  last used
  add-component                               projectSettings     ~100          -     0×  never
  anthropic-skills:xlsx                       claude.ai sync      < 20          -     0×  never
  jira-review                                 projectSettings     ~120          -    53×  19 days
  build-feature                               projectSettings     ~200       5.8m    54×  6 days
  my-grill-me                              userSettings        ~290     236.1k     3×  today

  context = this skill's one-line listing in the system prompt, included every turn
8 skills loaded but never invoked. Each one adds to the system prompt every turn.
"""


class ParseTest(unittest.TestCase):
    def test_reads_every_row(self):
        rows = parse(REPORT)
        self.assertEqual(list(rows), ["add-component", "anthropic-skills:xlsx", "jira-review",
                                      "build-feature", "my-grill-me"])

    def test_reads_the_columns(self):
        self.assertEqual(parse(REPORT)["build-feature"],
                         {"context": "~200", "tokens_7d": "5.8m", "uses": 54, "last_used": "6 days"})

    def test_a_source_with_a_space_and_a_tiny_context_still_read(self):
        self.assertEqual(parse(REPORT)["anthropic-skills:xlsx"],
                         {"context": "< 20", "tokens_7d": None, "uses": 0, "last_used": "never"})

    def test_text_without_a_table_reads_as_nothing(self):
        self.assertEqual(parse("Unknown command: /skill-doctor"), {})


class MatchTest(unittest.TestCase):
    def test_by_id_or_by_folder(self):
        skills = [
            {"id": "jira:review", "folder": "jira-review", "source": "project"},
            {"id": "anthropic-skills:xlsx", "folder": "xlsx", "source": "synced"},
            {"id": "tdd", "folder": "tdd", "source": "project"},
        ]
        rows = parse(REPORT)
        result = match(rows, skills)
        self.assertEqual(result["jira:review"]["uses"], 53)
        self.assertEqual(result["anthropic-skills:xlsx"]["uses"], 0)
        self.assertNotIn("tdd", result)

    def test_a_plugin_skill_is_not_matched_by_folder(self):
        skills = [{"id": "atlassian:add-component", "folder": "add-component", "source": "plugin"}]
        self.assertEqual(match(parse(REPORT), skills), {})


class UsageTest(unittest.TestCase):
    def test_fetches_in_the_background_and_keeps_the_result(self):
        gate = threading.Event()

        def report():
            gate.wait(5)
            return REPORT

        usage = Usage(report)
        usage.refresh()
        self.assertEqual(usage.state()["status"], "loading")
        gate.set()
        usage.wait(5)
        state = usage.state()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["rows"]["build-feature"]["uses"], 54)
        self.assertIsNotNone(state["fetched_at"])

    def test_a_failed_fetch_keeps_the_last_rows_and_says_why(self):
        answers = iter([REPORT, OSError("claude not found")])

        def report():
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        usage = Usage(report)
        usage.refresh()
        usage.wait(5)
        usage.refresh()
        usage.wait(5)
        state = usage.state()
        self.assertEqual(state["status"], "failed")
        self.assertIn("claude not found", state["error"])
        self.assertEqual(state["rows"]["jira-review"]["uses"], 53)

    def test_an_empty_report_is_a_failure(self):
        usage = Usage(lambda: "Unknown command")
        usage.refresh()
        usage.wait(5)
        self.assertEqual(usage.state()["status"], "failed")


if __name__ == "__main__":
    unittest.main()
