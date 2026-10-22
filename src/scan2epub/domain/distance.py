"""Bounded edit distance, used to keep the LLM corrector honest.

The corrector is only allowed to fix *recognition* errors. To enforce that, the
distance between the original and the corrected text is measured and, if it
exceeds a configurable threshold, the correction is discarded and the original
is kept.

The implementation is a banded (Ukkonen-style) Levenshtein distance: only the
cells within ``limit`` of the diagonal are evaluated, so the cost is
``O(len(a) * limit)`` instead of ``O(len(a) * len(b))``. That keeps the
guardrail cheap even for long paragraphs.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "levenshtein",
    "levenshtein_bounded",
    "normalized_distance",
]


def levenshtein_bounded(a: str, b: str, limit: int) -> int:  # noqa: PLR0911, PLR0912
    """Return the Levenshtein distance between ``a`` and ``b``.

    The computation stops as soon as it can prove that the distance is greater
    than ``limit``; in that case ``limit + 1`` is returned. The result is
    therefore exact when it is at most ``limit``.
    """
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1

    # Strip the common prefix and suffix: they never contribute to the
    # distance and they are by far the largest shared part in practice.
    start = 0
    end_a = len(a)
    end_b = len(b)
    while start < end_a and start < end_b and a[start] == b[start]:
        start += 1
    while end_a > start and end_b > start and a[end_a - 1] == b[end_b - 1]:
        end_a -= 1
        end_b -= 1

    row_a = a[start:end_a]
    row_b = b[start:end_b]
    if not row_a:
        return min(len(row_b), limit + 1)
    if not row_b:
        return min(len(row_a), limit + 1)
    if abs(len(row_a) - len(row_b)) > limit:
        return limit + 1

    # Swap so that the shorter string drives the columns.
    if len(row_a) < len(row_b):
        row_a, row_b = row_b, row_a

    n = len(row_b)
    previous = list(range(n + 1))
    current = [0] * (n + 1)
    threshold = limit + 1

    for i, char_a in enumerate(row_a, start=1):
        current[0] = i
        # Only cells with ``abs(i - j) <= limit`` can hold a value <= limit.
        lo = max(1, i - limit)
        hi = min(n, i + limit)
        if lo > 1:
            current[lo - 1] = threshold
        for j in range(lo, hi + 1):
            cost = 0 if char_a == row_b[j - 1] else 1
            value = min(
                previous[j] + 1,  # deletion
                current[j - 1] + 1,  # insertion
                previous[j - 1] + cost,  # substitution
            )
            current[j] = value
        if hi < n:
            current[hi + 1] = threshold
        if min(current[lo : hi + 1]) > limit:
            return threshold
        previous, current = current, previous

    distance = previous[n]
    return distance if distance <= limit else threshold


def levenshtein(a: Sequence[str], b: Sequence[str]) -> int:
    """Return the exact Levenshtein distance between two sequences.

    The sequences may be strings, or lists of words.

    Args:
        a: The first sequence.
        b: The second sequence.

    Returns:
        The number of insertions, deletions and substitutions that turn one
        sequence into the other.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    current = [0] * (len(b) + 1)
    for i, char_a in enumerate(a, start=1):
        current[0] = i
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
        previous, current = current, previous
    return previous[len(b)]


def normalized_distance(a: str, b: str) -> float:
    """Return the edit distance normalised by the length of the longer string.

    ``0.0`` means identical, ``1.0`` means completely different. The result is
    always in the ``0.0 .. 1.0`` range.
    """
    if a == b:
        return 0.0
    longest = max(len(a), len(b))
    if longest == 0:
        return 0.0
    return levenshtein(a, b) / longest
