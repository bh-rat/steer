import unittest

from steer import frontmatter


class TestSplit(unittest.TestCase):
    def test_split_basic(self):
        fm, body = frontmatter.split_document("---\nname: x\n---\nBody here\n")
        self.assertEqual(fm, "name: x\n")
        self.assertEqual(body, "Body here\n")

    def test_no_frontmatter(self):
        fm, body = frontmatter.split_document("Just a body\n")
        self.assertIsNone(fm)
        self.assertEqual(body, "Just a body\n")

    def test_unterminated(self):
        fm, body = frontmatter.split_document("---\nname: x\nno end")
        self.assertIsNone(fm)


class TestParse(unittest.TestCase):
    def test_scalars(self):
        data, problems = frontmatter.parse(
            'name: my-skill\ndescription: "Quoted: with colon"\nflag: true\n'
        )
        self.assertEqual(problems, [])
        self.assertEqual(data["name"], "my-skill")
        self.assertEqual(data["description"], "Quoted: with colon")
        self.assertIs(data["flag"], True)

    def test_unquoted_colon_lenient(self):
        # The most common authoring mistake: unquoted colon in description.
        data, problems = frontmatter.parse(
            "description: Does things: quickly and well\n"
        )
        self.assertEqual(data["description"], "Does things: quickly and well")

    def test_inline_list(self):
        data, _ = frontmatter.parse("allowed-tools: [Read, Bash]\n")
        self.assertEqual(data["allowed-tools"], ["Read", "Bash"])

    def test_block_list(self):
        data, _ = frontmatter.parse("items:\n  - one\n  - two\n")
        self.assertEqual(data["items"], ["one", "two"])

    def test_nested_map(self):
        data, _ = frontmatter.parse(
            'metadata:\n  version: "1.0"\n  author: jane\n'
        )
        self.assertEqual(data["metadata"], {"version": "1.0", "author": "jane"})

    def test_block_scalar_literal(self):
        data, _ = frontmatter.parse(
            "description: |\n  line one\n  line two\nname: x\n"
        )
        self.assertEqual(data["description"], "line one\nline two\n")
        self.assertEqual(data["name"], "x")

    def test_block_scalar_folded(self):
        data, _ = frontmatter.parse(
            "description: >-\n  long\n  folded text\n"
        )
        self.assertEqual(data["description"], "long folded text")

    def test_comments_skipped(self):
        data, problems = frontmatter.parse("# comment\nname: x\n")
        self.assertEqual(data, {"name": "x"})
        self.assertEqual(problems, [])

    def test_problems_reported(self):
        data, problems = frontmatter.parse("name: ok\njust junk no colon\n")
        self.assertEqual(data["name"], "ok")
        self.assertEqual(len(problems), 1)

    def test_double_quoted_unescapes(self):
        data, _ = frontmatter.parse(
            'description: "Say \\"ok\\": done. Match \\\\d+ digits."\n'
        )
        self.assertEqual(data["description"],
                         'Say "ok": done. Match \\d+ digits.')

    def test_single_quoted_unescapes(self):
        data, _ = frontmatter.parse("description: 'It''s here: now'\n")
        self.assertEqual(data["description"], "It's here: now")

    def test_nested_block_scalar_stops_at_sibling(self):
        data, _ = frontmatter.parse(
            "metadata:\n"
            "  notes: |\n"
            "    line one\n"
            "    line two\n"
            "  version: \"1.0\"\n"
        )
        self.assertEqual(data["metadata"]["notes"], "line one\nline two\n")
        self.assertEqual(data["metadata"]["version"], "1.0")

    def test_folded_scalar_keeps_paragraph_breaks(self):
        data, _ = frontmatter.parse(
            "description: >-\n"
            "  first para\n"
            "  still first\n"
            "\n"
            "  second para\n"
        )
        self.assertEqual(data["description"],
                         "first para still first\nsecond para")

    def test_bom_stripped(self):
        fm, _ = frontmatter.split_document("﻿---\nname: x\n---\nbody")
        self.assertEqual(fm, "name: x\n")


class TestEmit(unittest.TestCase):
    def test_roundtrip(self):
        original = {
            "name": "my-skill",
            "description": "Does things. Use when asked: nicely.",
            "metadata": {"version": "0.1.0", "author": "jane"},
        }
        text = frontmatter.emit(original)
        fm, _ = frontmatter.split_document(text + "body")
        parsed, problems = frontmatter.parse(fm)
        self.assertEqual(problems, [])
        self.assertEqual(parsed, original)

    def test_quoting_special(self):
        text = frontmatter.emit({"description": "has: colon"})
        self.assertIn('"has: colon"', text)

    def test_multiline_block(self):
        text = frontmatter.emit({"description": "one\ntwo"})
        self.assertIn("description: |", text)

    def test_roundtrip_backslash_and_quotes(self):
        # Regex-flavored descriptions must survive emit -> parse exactly;
        # the emitted escaping must also be what real YAML parsers expect.
        original = {"description": 'Matches \\d+ digits: say "done" after.'}
        text = frontmatter.emit(original)
        self.assertIn('\\\\d+', text)   # backslash escaped on disk
        fm, _ = frontmatter.split_document(text + "body")
        parsed, problems = frontmatter.parse(fm)
        self.assertEqual(problems, [])
        self.assertEqual(parsed, original)

    def test_roundtrip_hooks_structure(self):
        # The --auto-learn frontmatter: nested maps + list-of-maps.
        original = {
            "name": "x",
            "hooks": {"Stop": [{"hooks": [{
                "type": "command",
                "command": "steer learn reflect --skill x",
                "timeout": 15,
            }]}]},
        }
        text = frontmatter.emit(original)
        fm, _ = frontmatter.split_document(text + "body")
        parsed, problems = frontmatter.parse(fm)
        self.assertEqual(problems, [])
        self.assertEqual(parsed, original)


if __name__ == "__main__":
    unittest.main()
