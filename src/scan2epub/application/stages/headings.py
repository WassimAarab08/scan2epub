"""Heading detection.

A block becomes a heading only when several independent signals agree:
its length, its position on the page, its horizontal alignment, its
capitalisation or a known structural keyword. Anything else stays body text,
because a false heading breaks the table of contents and the chapter split.
"""

from __future__ import annotations

import re

from scan2epub.domain.models import TextBlock

__all__ = ["classify_heading", "is_heading_text"]

#: Keywords that introduce a structural division of an old book.
_STRUCTURAL_RE = re.compile(
    r"^\s*(cap[ií]tulo|libro|parte|tomo|ap[eé]ndice|anejo|anexo|pr[oó]logo|"
    r"introducci[oó]n|conclusi[oó]n|prefacio|contents|book|part|chapter|"
    r"appendix|prologue|preface|introduction|preliminaries)\b",
    re.IGNORECASE,
)

#: A bare Roman numeral used as a heading.
_ROMAN_RE = re.compile(r"^\s*[IVXLCDM]{1,7}\s*$")

#: A bare Arabic numeral used as a heading.
_ARABIC_RE = re.compile(r"^\s*\d{1,3}\s*$")

#: The maximum number of words a heading may have.
MAX_HEADING_WORDS = 14

#: The maximum number of characters a heading may have.
MAX_HEADING_CHARS = 120


def _letter_ratio_upper(text: str) -> float:
    """Return the ratio of uppercase letters in ``text``."""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(char.isupper() for char in letters) / len(letters)


def _is_centered(block: TextBlock) -> bool:
    """Whether the block is horizontally centred on the page."""
    return abs(block.bbox.center_x - 0.5) <= 0.1


def is_heading_text(text: str) -> bool:
    """Whether a text looks like a heading, ignoring its geometry."""
    stripped = " ".join(text.split())
    if not stripped or len(stripped) > MAX_HEADING_CHARS:
        return False
    words = stripped.split()
    if len(words) > MAX_HEADING_WORDS:
        return False
    if _STRUCTURAL_RE.match(stripped):
        return True
    if _ROMAN_RE.match(stripped):
        return True
    if _letter_ratio_upper(stripped) >= 0.85 and len(stripped) >= 3:
        return not (stripped.endswith((".", "!", "?")) and len(words) > 4)
    return False


def classify_heading(block: TextBlock) -> int | None:  # noqa: PLR0911
    """Decide whether a block is a heading, and at which level.

    Args:
        block: The block to classify.

    Returns:
        ``1`` for a chapter-level heading, ``2`` for a section-level heading,
        or ``None`` when the block is ordinary body text.
    """
    text = " ".join(block.text.split())
    if not text or len(text) > MAX_HEADING_CHARS:
        return None
    words = text.split()
    if len(words) > MAX_HEADING_WORDS:
        return None

    if _STRUCTURAL_RE.match(text):
        return 1
    if _ROMAN_RE.match(text):
        return 2

    if _letter_ratio_upper(text) >= 0.85 and len(text) >= 3:
        # An all-capitals line is a heading, unless it reads like a shouted
        # sentence.
        if text.endswith((".", "!", "?")) and len(words) > 4:
            return None
        return 2

    if (
        _is_centered(block)
        and block.bbox.width < 0.78
        and block.bbox.y0 < 0.5
        and not text.endswith((".", "!", "?"))
    ):
        return 2

    if _ARABIC_RE.match(text) and _is_centered(block):
        return 2

    return None
