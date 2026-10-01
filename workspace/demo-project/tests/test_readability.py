"""Tests for textmetrics.readability. Owned by worker 2."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from textmetrics.readability import (  # noqa: E402
    average_words_per_sentence,
    count_sentences,
    count_syllables,
    flesch_reading_ease,
)


class TestCountSentences(unittest.TestCase):
    def test_single(self):
        self.assertEqual(count_sentences("One thing."), 1)

    def test_three(self):
        self.assertEqual(
            count_sentences("One. Two? Three!"), 3
        )

    def test_runs_of_terminators_are_one_sentence(self):
        self.assertEqual(count_sentences("Wait... what? Really!!!"), 3)

    def test_empty(self):
        self.assertEqual(count_sentences(""), 0)

    def test_whitespace_only(self):
        self.assertEqual(count_sentences("   \n  "), 0)

    def test_no_terminator_still_counts_one(self):
        self.assertEqual(count_sentences("no terminator here"), 1)


class TestAverageWordsPerSentence(unittest.TestCase):
    def test_average(self):
        self.assertAlmostEqual(average_words_per_sentence("Two words here. Ok."), 2.5)

    def test_empty_is_zero(self):
        self.assertEqual(average_words_per_sentence(""), 0.0)

    def test_whitespace_only_is_zero(self):
        self.assertEqual(average_words_per_sentence("  "), 0.0)

    def test_returns_float(self):
        self.assertIsInstance(average_words_per_sentence("a. b."), float)


class TestCountSyllables(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(count_syllables("cat"), 1)

    def test_two_syllables(self):
        self.assertEqual(count_syllables("table"), 2)

    def test_empty_is_zero(self):
        self.assertEqual(count_syllables(""), 0)

    def test_consonant_only_word_is_at_least_one(self):
        self.assertGreaterEqual(count_syllables("rhythm"), 1)
        self.assertGreaterEqual(count_syllables("hmm"), 1)

    def test_ignores_case(self):
        self.assertEqual(count_syllables("CAT"), count_syllables("cat"))


class TestFleschReadingEase(unittest.TestCase):
    def test_returns_float(self):
        self.assertIsInstance(flesch_reading_ease("The cat sat. It was happy."), float)

    def test_empty_is_zero(self):
        self.assertEqual(flesch_reading_ease(""), 0.0)

    def test_whitespace_only_is_zero(self):
        self.assertEqual(flesch_reading_ease("   "), 0.0)

    def test_rounded_to_two_places(self):
        value = flesch_reading_ease("The extraordinarily complicated bureaucracy " * 3)
        self.assertEqual(value, round(value, 2))

    def test_simple_text_scores_higher_than_complex(self):
        simple = flesch_reading_ease("The cat sat on the mat. The dog ran. It was fun.")
        complex_ = flesch_reading_ease(
            "The extraordinarily complicated bureaucratic methodologies "
            "predetermine institutional implementations. "
            "Notwithstanding the aforementioned considerations, "
            "the aforementioned administration determines implementations."
        )
        self.assertGreater(simple, complex_)


if __name__ == "__main__":
    unittest.main()