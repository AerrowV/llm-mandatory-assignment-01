"""Sentence counts and readability scores. Owned by worker 2."""

from __future__ import annotations


def count_sentences(text: str) -> int:
    """Sentences split on . ! ? - runs of terminators count as one.

    Edge case: empty or whitespace-only input returns 0.
    """
    raise NotImplementedError("count_sentences is a stub")


def average_words_per_sentence(text: str) -> float:
    """0.0 when there are no sentences, so callers need no guard.

    Edge case: returns a float always, including for empty input.
    """
    raise NotImplementedError("average_words_per_sentence is a stub")


def count_syllables(word: str) -> int:
    """Vowel-group heuristic. Every word counts at least one syllable.

    Edge case: empty string is 0, but any non-empty word is at least 1.
    """
    raise NotImplementedError("count_syllables is a stub")


def flesch_reading_ease(text: str) -> float:
    """206.85 - 1.015*(words/sentences) - 84.6*(syllables/words). 0.0 if no words.

    Edge case: rounded to two decimals; may be negative, do not clamp.
    """
    raise NotImplementedError("flesch_reading_ease is a stub")