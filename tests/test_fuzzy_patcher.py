"""
Tests for Multi-Stage Fuzzy Patcher.
"""

import unittest

from lucy.core.fuzzy_patcher import FuzzyPatcher


class TestFuzzyPatcher(unittest.TestCase):
    def test_exact_match(self):
        content = "def foo():\n    return 42\n"
        old = "    return 42"
        new = "    return 100"
        res = FuzzyPatcher.apply_patch(content, old, new)
        self.assertTrue(res.success)
        self.assertEqual(res.stage_used, "exact")
        self.assertIn("return 100", res.new_content)

    def test_whitespace_drift_trailing_spaces(self):
        content = "def add(a, b):   \n    return a + b  \n"
        old = "def add(a, b):\n    return a + b"
        new = "def add(a, b):\n    # add doc\n    return a + b"
        res = FuzzyPatcher.apply_patch(content, old, new)
        self.assertTrue(res.success)
        self.assertEqual(res.stage_used, "whitespace_normalized")
        self.assertIn("# add doc", res.new_content)

    def test_indentation_shift(self):
        content = "class Greeter:\n        def greet(self):\n            print('hi')\n"
        # LLM provided unindented or 4-space indented version instead of 8 spaces
        old = "    def greet(self):\n        print('hi')"
        new = "    def greet(self):\n        print('hello world')"
        res = FuzzyPatcher.apply_patch(content, old, new)
        self.assertTrue(res.success)
        self.assertIn(res.stage_used, ("indentation_normalized", "anchor_fuzzy"))
        self.assertIn("print('hello world')", res.new_content)

    def test_search_replace_block_syntax(self):
        content = "x = 10\ny = 20\nz = x + y\n"
        old = "<<<<<<< SEARCH\ny = 20\n=======\ny = 50\n>>>>>>> REPLACE"
        res = FuzzyPatcher.apply_patch(content, old, "")
        self.assertTrue(res.success)
        self.assertIn("y = 50", res.new_content)

    def test_ambiguous_target(self):
        content = "x = 1\nx = 1\n"
        res = FuzzyPatcher.apply_patch(content, "x = 1", "x = 2")
        self.assertFalse(res.success)
        self.assertIn("appears 2 times", res.error)


if __name__ == "__main__":
    unittest.main()

