"""Word splitting, counting and frequency helpers. Owned by worker 1."""

from __future__ import annotations


def split_words(text: str) -> list[str]:
    """Lowercase, then split on any run of non-alphanumeric characters.

    Edge case: empty or separator-only input returns an empty list.
    """
    raise NotImplementedError("split_words is a stub")


def count_words(text: str, stopwords: set[str] | None = None) -> int:
    """Number of words after removing stopwords. Case-insensitive.

    Edge case: a stopword set that removes every word yields 0, not 1.
    """
    raise NotImplementedError("count_words is a stub")


def word_frequencies(text: str) -> dict[str, int]:
    """Counts per distinct word, lowercased, most frequent first.

    Edge case: empty input returns an empty dict, never None.
    """
    raise NotImplementedError("word_frequencies is a stub")


def top_n(text: str, n: int) -> list[tuple[str, int]]:
    """The n most frequent (word, count) pairs. Ties break alphabetically.

    Edge case: n <= 0 returns an empty list; n beyond the vocabulary returns
    everything available.
    """
    raise NotImplementedError("top_n is a stub")