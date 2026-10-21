"""Tests for the bounded edit distance used by the correction guardrail."""

from __future__ import annotations

import pytest

from scan2epub.domain.distance import levenshtein, levenshtein_bounded, normalized_distance


def test_identical_strings_have_no_distance() -> None:
    """Identical strings are at distance zero."""
    assert levenshtein("hola", "hola") == 0
    assert normalized_distance("hola", "hola") == 0.0


def test_levenshtein_counts_the_edits() -> None:
    """The classic examples give the expected distance."""
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("", "abc") == 3
    assert levenshtein("abc", "") == 3


def test_normalized_distance_is_bounded() -> None:
    """The normalised distance never exceeds one."""
    assert normalized_distance("abc", "xyz") == 1.0
    assert normalized_distance("abc", "abd") == pytest.approx(1 / 3)


def test_bounded_distance_is_exact_below_the_limit() -> None:
    """Below the limit the result is the exact distance."""
    assert levenshtein_bounded("kitten", "sitting", 10) == 3
    assert levenshtein_bounded("hola", "hola", 5) == 0


def test_bounded_distance_caps_above_the_limit() -> None:
    """Above the limit the result is the limit plus one."""
    assert levenshtein_bounded("kitten", "sitting", 1) == 2
    assert levenshtein_bounded("a", "b", 0) == 1


def test_bounded_distance_rejects_impossible_lengths() -> None:
    """A length difference above the limit is detected immediately."""
    assert levenshtein_bounded("a", "aaaaaaaaaa", 3) == 4


def test_bounded_distance_handles_empty_strings() -> None:
    """Empty inputs are handled."""
    assert levenshtein_bounded("", "", 3) == 0
    assert levenshtein_bounded("", "ab", 3) == 2
    assert levenshtein_bounded("ab", "", 3) == 2


def test_bounded_distance_rejects_a_negative_limit() -> None:
    """A negative limit is a programming error."""
    with pytest.raises(ValueError):
        levenshtein_bounded("a", "b", -1)


def test_bounded_distance_agrees_with_the_exact_distance() -> None:
    """The banded implementation matches the naive one."""
    for a, b in (("", ""), ("a", ""), ("abc", "abd"), ("hola", "hola"), ("x" * 40, "y" * 40)):
        assert levenshtein_bounded(a, b, 100) == levenshtein(a, b)


def test_bounded_distance_is_fast_on_long_text() -> None:
    """The banded implementation stays cheap on long paragraphs."""
    text = "palabra " * 500
    assert levenshtein_bounded(text, text.replace("palabra", "palabras"), 3) == 4
