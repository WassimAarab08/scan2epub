"""The metrics of the evaluation: the CER and the WER.

The two numbers answer different questions:

* the **CER** (character error rate) measures the characters. It is the right
  number for a historical book, where the long s and the ligatures are the
  main source of error.
* the **WER** (word error rate) measures the words. It is the right number for
  a modern book.

Both are computed on the *whole* book at once, not page by page: a page by
page score would hide the errors that the cleaner repairs.
"""

from __future__ import annotations

import re
import unicodedata

from scan2epub.domain.distance import levenshtein

__all__ = [
    "character_error_rate",
    "normalise",
    "word_error_rate",
    "word_tokens",
]

#: The characters that are removed before the comparison.
_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)

#: The runs of blanks.
_SPACES_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Return the text in the form that the two metrics compare.

    The typography is removed: the case, the punctuation and the accents do
    not change the words, so they must not count as errors. The long s is
    normalised as well, because the reference transcription never has it.

    Args:
        text: The text to normalise.

    Returns:
        The normalised text.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ſ", "s")
    text = text.casefold()
    text = _PUNCTUATION_RE.sub(" ", text)
    return _SPACES_RE.sub(" ", text).strip()


def word_tokens(text: str) -> list[str]:
    """Return the words of a text, in the form that the WER compares."""
    normalised = normalise(text)
    return normalised.split() if normalised else []


def _rate(hypothesis: list[str], reference: list[str]) -> float:
    """Return the edit distance divided by the length of the reference."""
    if not reference:
        # An empty reference: the error rate is zero when the hypothesis is
        # empty too, and infinite otherwise.
        return 0.0 if not hypothesis else 1.0
    return levenshtein(hypothesis, reference) / len(reference)


def character_error_rate(hypothesis: str, reference: str) -> float:
    """Return the character error rate of a hypothesis.

    Args:
        hypothesis: The text that was recognised.
        reference: The text that was expected.

    Returns:
        The error rate, between `0.0` (perfect) and `1.0` (completely wrong).
    """
    return _rate(list(normalise(hypothesis)), list(normalise(reference)))


def word_error_rate(hypothesis: str, reference: str) -> float:
    """Return the word error rate of a hypothesis.

    Args:
        hypothesis: The text that was recognised.
        reference: The text that was expected.

    Returns:
        The error rate, between `0.0` (perfect) and `1.0` (completely wrong).
    """
    return _rate(word_tokens(hypothesis), word_tokens(reference))
