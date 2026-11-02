"""The frontmatter reader covers what real skills use: scalars, quoted strings, block scalars,
lists and one nested map. Anything else is a FrontmatterError, never a crash."""

import unittest

from sx.frontmatter import FrontmatterError, parse


def doc(frontmatter, body="# Body\n"):
    return f"---\n{frontmatter}\n---\n{body}"


class SplitTest(unittest.TestCase):
    def test_no_frontmatter_leaves_the_whole_text_as_body(self):
        fm, body = parse("# Just a body\n")
        self.assertIsNone(fm)
        self.assertEqual(body, "# Just a body\n")

    def test_body_follows_the_closing_fence(self):
        fm, body = parse(doc("name: a", "line one\nline two\n"))
        self.assertEqual(fm, {"name": "a"})
        self.assertEqual(body, "line one\nline two\n")

    def test_unclosed_frontmatter_is_an_error(self):
        with self.assertRaises(FrontmatterError):
            parse("---\nname: a\n# no closing fence\n")


class ScalarTest(unittest.TestCase):
    def test_plain_scalar(self):
        self.assertEqual(parse(doc("name: brain-tdd"))[0], {"name": "brain-tdd"})

    def test_double_quoted_keeps_colons_and_dashes(self):
        fm, _ = parse(doc('description: "Use when: the user says \'TDD\' — or not."'))
        self.assertEqual(fm["description"], "Use when: the user says 'TDD' — or not.")

    def test_double_quoted_escapes(self):
        fm, _ = parse(doc(r'description: "a \"quoted\" word"'))
        self.assertEqual(fm["description"], 'a "quoted" word')

    def test_single_quoted_doubles_its_quote(self):
        fm, _ = parse(doc("description: 'it''s fine: really'"))
        self.assertEqual(fm["description"], "it's fine: really")

    def test_comment_after_plain_scalar_is_dropped(self):
        fm, _ = parse(doc("name: a # the name\n# a whole-line comment"))
        self.assertEqual(fm, {"name": "a"})

    def test_empty_value_is_none(self):
        self.assertEqual(parse(doc("license:"))[0], {"license": None})

    def test_unterminated_quote_is_an_error(self):
        with self.assertRaises(FrontmatterError):
            parse(doc('description: "never closed'))


class BlockScalarTest(unittest.TestCase):
    def test_folded_joins_lines_with_spaces(self):
        fm, _ = parse(doc("description: >\n  one line\n  and the next\nname: a"))
        self.assertEqual(fm["description"], "one line and the next\n")
        self.assertEqual(fm["name"], "a")

    def test_literal_keeps_newlines(self):
        fm, _ = parse(doc("description: |\n  one line\n  and the next"))
        self.assertEqual(fm["description"], "one line\nand the next\n")

    def test_strip_chomping_drops_the_final_newline(self):
        fm, _ = parse(doc("description: >-\n  one\n  two"))
        self.assertEqual(fm["description"], "one two")


class ListTest(unittest.TestCase):
    def test_block_list(self):
        fm, _ = parse(doc("tags:\n  - a\n  - 'b: c'"))
        self.assertEqual(fm["tags"], ["a", "b: c"])

    def test_flow_list(self):
        fm, _ = parse(doc("tags: [a, 'b, c', d]"))
        self.assertEqual(fm["tags"], ["a", "b, c", "d"])


class NestedMapTest(unittest.TestCase):
    def test_metadata_map(self):
        fm, _ = parse(doc(
            "name: a\nmetadata:\n  type: reference\n  last_verified: 2026-09-03\n"
            "  extracted_from: a working project skill, 2026-08-24\nlicense: MIT"
        ))
        self.assertEqual(fm["metadata"], {
            "type": "reference",
            "last_verified": "2026-09-03",
            "extracted_from": "a working project skill, 2026-08-24",
        })
        self.assertEqual(fm["license"], "MIT")

    def test_list_inside_map(self):
        fm, _ = parse(doc("metadata:\n  tags:\n    - x\n    - y"))
        self.assertEqual(fm["metadata"], {"tags": ["x", "y"]})


class BrokenTest(unittest.TestCase):
    def test_line_without_a_key_is_an_error(self):
        with self.assertRaises(FrontmatterError) as caught:
            parse(doc("name: a\nthis is not yaml"))
        self.assertIn("line 2", str(caught.exception))

    def test_frontmatter_that_is_not_a_map_is_an_error(self):
        with self.assertRaises(FrontmatterError):
            parse(doc("- a\n- b"))


if __name__ == "__main__":
    unittest.main()
