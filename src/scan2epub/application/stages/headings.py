"""Heading detection.

A block becomes a heading only when several independent signals agree:
its length, its position on the page, its horizontal alignment, its
capitalisation, its typography or a known structural keyword. Anything else
stays body text, because a false heading breaks the table of contents and
the chapter split.

The typography is the strongest signal of a printed page: a title is set in
a bigger type than the body, so the blocks are classified with the page in
hand and not one by one.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from scan2epub.domain.models import BlockKind, TextBlock

__all__ = [
    "classify_heading",
    "classify_page",
    "is_display_type",
    "is_heading_text",
    "typical_line_height",
]

#: Keywords that introduce a structural division of an old book.
_STRUCTURAL_RE = re.compile(
    r"^\s*(cap[ií]tulo|libro|parte|tomo|ap[eé]ndice|anejo|anexo|pr[oó]logo|"
    r"introducci[oó]n|conclusi[oó]n|prefacio|contents|book|part|chapter|"
    r"appendix|prologue|preface|introduction|preliminaries)\b\s*(.*)$",
    re.IGNORECASE,
)

#: A number or a Roman numeral after the structural keyword.
_ORDINAL_RE = re.compile(r"^(?:[0-9]{1,4}|[IVXLCDM]{1,7})$", re.IGNORECASE)

#: A bare Roman numeral used as a heading.
_ROMAN_RE = re.compile(r"^\s*[IVXLCDM]{1,7}\s*$")

#: A bare Arabic numeral used as a heading.
_ARABIC_RE = re.compile(r"^\s*\d{1,3}\s*$")

#: The maximum number of words a heading may have.
MAX_HEADING_WORDS = 14

#: The maximum number of characters a heading may have.
MAX_HEADING_CHARS = 120

#: The most words and characters of a title set in display type.
MAX_TITLE_WORDS = 40

#: The most characters of a title set in display type.
MAX_TITLE_CHARS = 300

#: How much bigger than the body a block must be to count as display type.
DISPLAY_RATIO = 1.35


def _letter_ratio_upper(text: str) -> float:
    """Return the ratio of uppercase letters in ``text``."""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(char.isupper() for char in letters) / len(letters)


def _is_centered(block: TextBlock) -> bool:
    """Whether the block is horizontally centred on the page."""
    return abs(block.bbox.center_x - 0.5) <= 0.1


def _line_height(block: TextBlock) -> float:
    """Return the height of one line of the block, in page fractions."""
    return block.bbox.height / max(1, len(block.lines))


def typical_line_height(blocks: Sequence[TextBlock]) -> float:
    """Return the height of a line of body text.

    The median is weighted by the number of lines of every block, so the
    few blocks that the page sets in display type never become the
    reference of the page.

    Args:
        blocks: The blocks of one page.

    Returns:
        The height of a line, in page fractions, or ``0`` when there is
        nothing to measure.
    """
    samples = sorted(
        (_line_height(block), max(1, len(block.lines))) for block in blocks if block.bbox.height > 0
    )
    if not samples:
        return 0.0
    total = sum(count for _, count in samples)
    running = 0
    for height, count in samples:
        running += count
        if running * 2 >= total:
            return height
    return samples[-1][0]


def is_display_type(block: TextBlock, typical: float) -> bool:
    """Whether a block is set in a bigger type than the body of the page."""
    if typical <= 0:
        return False
    return _line_height(block) >= typical * DISPLAY_RATIO


def is_structural_heading(text: str) -> bool:
    """Whether a text introduces a structural division of the book.

    The keyword alone is not enough: "Book the tickets" and "Part of the
    problem" are ordinary sentences. A heading names the division with a
    number, with a Roman numeral, or with a capitalised word, and it is
    short.
    """
    match = _STRUCTURAL_RE.match(text)
    if match is None:
        return False
    rest = match.group(2).strip()
    if not rest:
        # The bare keyword is a heading: "Chapter", "INTRODUCCION".
        return True
    if _ORDINAL_RE.match(rest):
        return True
    # A capitalised word, in a short line. A lower-case word after the
    # keyword means a sentence: "Book the tickets", "Part of the problem".
    return rest[:1].isupper() and len(text) <= 60


def is_heading_text(text: str) -> bool:
    """Whether a text looks like a heading, ignoring its geometry."""
    stripped = " ".join(text.split())
    if not stripped or len(stripped) > MAX_HEADING_CHARS:
        return False
    words = stripped.split()
    if len(words) > MAX_HEADING_WORDS:
        return False
    if is_structural_heading(stripped):
        return True
    if _ROMAN_RE.match(stripped):
        return True
    if _letter_ratio_upper(stripped) >= 0.85 and len(stripped) >= 3:
        return not (stripped.endswith((".", "!", "?")) and len(words) > 4)
    return False


def classify_heading(  # noqa: PLR0911
    block: TextBlock,
    *,
    display: bool = False,
    page_title: bool = False,
) -> int | None:
    """Decide whether a block is a heading, and at which level.

    Args:
        block: The block to classify.
        display: Whether the block is set in a bigger type than the body.
        page_title: Whether the block is the first one set in display type
            on its page, which makes it the title of the page.

    Returns:
        ``1`` for a chapter-level heading, ``2`` for a section-level heading,
        or ``None`` when the block is ordinary body text.
    """
    text = " ".join(block.text.split())
    if not text:
        return None
    words = text.split()

    if is_structural_heading(text):
        return 1
    if _ROMAN_RE.match(text):
        return 2

    # The title of a page is set in a bigger type than the body. It may be
    # long, and it may end with a period, the way the titles of the articles
    # of the 19th and the 20th centuries do.
    if page_title and len(words) <= MAX_TITLE_WORDS and len(text) <= MAX_TITLE_CHARS:
        return 2

    if display:
        # A byline, a subtitle or a dedication: the block follows the title
        # and it is set in a big type too. Only the capitals say that it is
        # a heading of its own.
        if _letter_ratio_upper(text) >= 0.85 and len(words) <= 8:
            return 2
        return None

    if len(words) > MAX_HEADING_WORDS or len(text) > MAX_HEADING_CHARS:
        return None

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


def classify_page(blocks: Sequence[TextBlock]) -> list[int | None]:
    """Classify every block of a page, in reading order.

    The typography of the page is used as one more signal: the first block
    that is set in a bigger type than the body is the title of the page, and
    the blocks that follow it in the same type are not headings unless their
    text says so.

    Args:
        blocks: The blocks of one page, in reading order.

    Returns:
        The level of every block, or ``None`` when it is body text.
    """
    # Only the body text sets the measure of the page: the footnotes, the
    # headings that another stage already marked and the illustrations are
    # set in other sizes and would distort the median.
    body = [block for block in blocks if block.kind is BlockKind.BODY]
    typical = typical_line_height(body or blocks)
    levels: list[int | None] = []
    title_pending = True
    for block in blocks:
        display = is_display_type(block, typical)
        # The title of a page is the first block set in a big type, centred
        # and narrower than the measure of the page. A full-width block in a
        # big type is a quotation or a line of a poem, not a title.
        title = display and title_pending and _is_centered(block) and block.bbox.width < 0.9
        if display:
            title_pending = False
        levels.append(classify_heading(block, display=display, page_title=title))
    return levels
