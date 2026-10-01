"""Small text-measurement library used as the pipeline's demo target.

Two modules, owned by two workers:

- `tokens`      word splitting, counting, frequencies
- `readability` sentence counts and readability scores
"""

from textmetrics.readability import (
    average_words_per_sentence,
    count_sentences,
    count_syllables,
    flesch_reading_ease,
)
from textmetrics.tokens import (
    count_words,
    split_words,
    top_n,
    word_frequencies,
)

__all__ = [
    "average_words_per_sentence",
    "count_sentences",
    "count_syllables",
    "count_words",
    "flesch_reading_ease",
    "split_words",
    "top_n",
    "word_frequencies",
]