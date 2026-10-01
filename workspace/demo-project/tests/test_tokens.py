"""Tests for textmetrics.tokens. Owned by worker 1."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from textmetrics.tokens import (  # noqa: E402
    count_words,
    split_words,
    top_n,
    word_frequencies,
)


class TestSplitWords(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(split_words("hello world"), ["hello", "world"])

    def test_lowercases(self):
        self.assertEqual(split_words("Hello World"), ["hello", "world"])

    def test_empty(self):
        self.assertEqual(split_words(""), [])

    def test_only_separators(self):
        self.assertEqual(split_words("   ,,,  "), [])

    def test_punctuation_and_underscore_are_separators(self):
        self.assertEqual(split_words("a,b_c1"), ["a", "b", "c", "1"])

    def test_runs_of_separators_collapse(self):
        self.assertEqual(split_words("a   b"), ["a", "b"])

    def test_newlines(self):
        self.assertEqual(split_words("one\ntwo\tthree"), ["one", "two", "three"])


class TestCountWords(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(count_words("one two three"), 3)

    def test_no_stopwords(self):
        self.assertEqual(count_words("one two three"), 3)

    def test_removes_stopwords(self):
        self.assertEqual(count_words("the cat and the hat", {"the", "and"}), 3)

    def test_stopwords_case_insensitive(self):
        self.assertEqual(count_words("The cat AND the hat", {"THE", "and"}), 3)

    def test_every_word_stopped_yields_zero(self):
        self.assertEqual(count_words("the and", {"the", "and"}), 0)

    def test_empty(self):
        self.assertEqual(count_words(""), 0)


class TestWordFrequencies(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(word_frequencies("a b a"), {"a": 2, "b": 1})

    def test_empty_is_empty_dict(self):
        self.assertEqual(word_frequencies(""), {})

    def test_sorted_most_frequent_first(self):
        freqs = word_frequencies("a b c c c")
        self.assertEqual(list(freqs), ["c", "a", "b"])

    def test_lowercased(self):
        self.assertEqual(word_frequencies("Word word"), {"word": 2})


class TestTopN(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(top_n("a b a", 2), [("a", 2), ("b", 1)])

    def test_zero(self):
        self.assertEqual(top_n("a b", 0), [])

    def test_negative(self):
        self.assertEqual(top_n("a b", -3), [])

    def test_more_than_available(self):
        self.assertEqual(top_n("a b", 10), [("a", 1), ("b", 1)])

    def test_ties_break_alphabetically(self):
        self.assertEqual(top_n("b a", 2), [("a", 1), ("b", 1)])

    def test_empty_text(self):
        self.assertEqual(top_n("", 5), [])


if __name__ == "__main__":
    unittest.main()