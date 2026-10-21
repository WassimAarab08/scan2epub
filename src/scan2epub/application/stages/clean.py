"""Deterministic text cleaning.

This stage runs **before** any model and never rewrites the text. It only
repairs the mechanical damage that scanning and old printing produce:

* running heads, folios and page numbers are removed;
* the lines that belong to the same paragraph are gathered back together;
* words broken by a hyphen at the end of a line are rejoined;
* the long s and the Latin ligatures are normalised;
* paragraphs that continue on the next page are merged.

Every rule is a pure function of the recognised text and its geometry, so the
result is reproducible: running the pipeline twice gives the same book.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scan2epub.application.stages.headings import classify_heading
from scan2epub.config import CleanConfig
from scan2epub.domain.models import BlockKind, PageContent, TextBlock
from scan2epub.domain.normalize import folded, normalize_line

__all__ = ["CleanResult", "clean_pages"]

#: Characters that can end a sentence and therefore end a paragraph.
_TERMINAL_PUNCTUATION = frozenset(".!?…:;»”\"')]}")

#: A block made only of digits and punctuation is a page number.
_PAGE_NUMBER_RE = re.compile(r"^[^0-9A-Za-z]*\d{1,5}[^0-9A-Za-z]*$")

#: A footnote marker at the beginning of a block.
_FOOTNOTE_RE = re.compile(r"^\s*[\(\[]?(\d{1,3})[\)\].:]?\s+\S")

#: A word continuation after a hyphen always starts with a lowercase letter.
_CONTINUATION_RE = re.compile(r"^[a-záéíóúüñçàèìòùâêîôûäëïöüãõæœß]")


@dataclass(frozen=True, slots=True)
class CleanResult:
    """The outcome of the deterministic cleaning pass."""

    pages: tuple[PageContent, ...] = ()
    removed_running_heads: tuple[str, ...] = ()
    removed_page_numbers: int = 0
    joined_hyphens: int = 0
    merged_paragraphs: int = 0
    detected_footnotes: int = 0


def _is_in_zone(block: TextBlock, zone: float, *, top: bool) -> bool:
    """Whether a block lies inside a header or footer zone of the page."""
    if top:
        return block.bbox.y1 <= zone
    return block.bbox.y0 >= 1.0 - zone


def _is_running_head_candidate(block: TextBlock, config: CleanConfig) -> bool:
    """Whether a block may be a running head or a folio."""
    text = " ".join(block.text.split())
    if not text or len(text) > config.max_running_head_chars:
        return False
    if block.kind is BlockKind.FOOTNOTE:
        # A numbered note at the bottom of the page is a footnote, not a
        # running head, even when the same note is repeated.
        return False
    in_header = _is_in_zone(block, config.header_zone, top=True)
    in_footer = _is_in_zone(block, config.footer_zone, top=False)
    return in_header or in_footer


def _find_repeated_blocks(
    pages: list[PageContent], config: CleanConfig
) -> tuple[set[tuple[int, int]], set[str]]:
    """Return the blocks that repeat across pages, and the repeated texts.

    A running head is a short block that appears in a header or footer zone
    on at least ``min_running_head_repeats`` distinct pages. A block that
    only exists on a single page is *not* a running head: it is content.
    """
    occurrences: dict[str, list[tuple[int, int]]] = {}
    texts: dict[str, str] = {}
    for page in pages:
        for block in page.blocks:
            if not _is_running_head_candidate(block, config):
                continue
            key = folded(block.text)
            if not key:
                continue
            occurrences.setdefault(key, []).append((page.index, block.order))
            texts.setdefault(key, " ".join(block.text.split()))

    repeated: set[tuple[int, int]] = set()
    repeated_texts: set[str] = set()
    for key, positions in occurrences.items():
        distinct_pages = {page_index for page_index, _ in positions}
        if len(distinct_pages) < config.min_running_head_repeats:
            continue
        repeated.update(positions)
        repeated_texts.add(texts[key])
    return repeated, repeated_texts


def _join_hyphenated_lines(lines: tuple[str, ...]) -> tuple[tuple[str, ...], int]:
    """Rejoin the words that were split by a hyphen at the end of a line."""
    if not lines:
        return lines, 0
    result: list[str] = []
    joins = 0
    for line in lines:
        if result:
            previous = result[-1]
            stripped = previous.rstrip()
            # The hyphen must touch the word: "casa -" is a dash, not a
            # hyphenation.
            if (
                stripped.endswith("-")
                and not stripped.endswith(" -")
                and len(stripped) > 1
                and stripped[-2].isalpha()
                and _CONTINUATION_RE.match(line)
            ):
                result[-1] = stripped[:-1] + line
                joins += 1
                continue
        result.append(line)
    return tuple(result), joins


def _ends_sentence(text: str) -> bool:
    """Whether the text ends with sentence-final punctuation."""
    stripped = text.rstrip()
    if not stripped:
        return True
    return stripped[-1] in _TERMINAL_PUNCTUATION


def _continues_previous(previous: str, following: str) -> bool:
    """Whether ``following`` continues the paragraph opened by ``previous``."""
    if not previous or not following:
        return False
    if _ends_sentence(previous):
        return False
    if previous.rstrip().endswith("-"):
        # The word was broken at the end of the line: always continue.
        return True
    # A line that does not close a sentence continues the paragraph, unless
    # the next block clearly starts a new one.
    if following[:1].isupper() and following[:1].isascii():
        # Uppercase start: only continue when the previous line ends with a
        # comma or a conjunction-like continuation.
        return previous.rstrip().endswith((",", ";", "y", "e", "o", "u", "i", "—", "–"))
    return True


def _merge_into_paragraphs(blocks: list[TextBlock]) -> tuple[list[TextBlock], int, int]:
    """Gather the lines that belong to the same paragraph.

    OCR engines regularly return one block per printed line. The blocks are
    merged back together when the previous one does not close a sentence.

    A footnote does not interrupt a paragraph: the text that follows a note
    at the bottom of a page often continues the paragraph that started on the
    previous page. A heading, on the other hand, always ends a paragraph.

    Returns:
        The merged blocks, the number of merges and the number of words that
        were rejoined across a hyphen.
    """
    if not blocks:
        return blocks, 0, 0

    merged: list[TextBlock] = []
    last_body: int | None = None
    merges = 0
    hyphen_joins = 0
    for block in blocks:
        if block.kind is BlockKind.HEADING:
            merged.append(block)
            last_body = None
            continue
        if block.kind is not BlockKind.BODY:
            # Footnotes and illustrations do not break the paragraph.
            merged.append(block)
            continue
        if last_body is not None:
            previous = merged[last_body]
            previous_text = " ".join(previous.text.split())
            current_text = " ".join(block.text.split())
            if _continues_previous(previous_text, current_text):
                if previous_text.rstrip().endswith("-"):
                    # The word itself was broken: drop the hyphen and glue
                    # the two halves together without a space.
                    head = previous.lines[:-1]
                    first = block.lines[0] if block.lines else ""
                    joined = previous.lines[-1].rstrip()[:-1] + first
                    rest = block.lines[1:]
                    lines = (*head, joined, *rest)
                    hyphen_joins += 1
                else:
                    lines = previous.lines + block.lines
                merged[last_body] = previous.with_lines(lines)
                merges += 1
                continue
        merged.append(block)
        last_body = len(merged) - 1
    return merged, merges, hyphen_joins


def _detect_footnotes(blocks: list[TextBlock], config: CleanConfig) -> tuple[list[TextBlock], int]:
    """Mark the blocks that look like footnotes."""
    detected = 0
    marked: list[TextBlock] = []
    for block in blocks:
        candidate = block
        if (
            candidate.kind is BlockKind.BODY
            and candidate.bbox.y0 >= config.footnote_zone
            and _FOOTNOTE_RE.match(" ".join(candidate.text.split())) is not None
        ):
            candidate = candidate.with_kind(BlockKind.FOOTNOTE)
            detected += 1
        marked.append(candidate)
    return marked, detected


def _mark_headings(blocks: list[TextBlock]) -> list[TextBlock]:
    """Mark the blocks that look like headings."""
    marked: list[TextBlock] = []
    for block in blocks:
        candidate = block
        if candidate.kind is BlockKind.BODY:
            level = classify_heading(candidate)
            if level is not None:
                candidate = candidate.with_kind(BlockKind.HEADING).with_level(level)
        marked.append(candidate)
    return marked


def clean_pages(pages: list[PageContent], config: CleanConfig | None = None) -> CleanResult:
    """Clean the recognised text of a whole book.

    Args:
        pages: The recognised pages, in reading order.
        config: The cleaning options. Defaults are used when omitted.

    Returns:
        The cleaned pages together with a summary of what was changed.
    """
    config = config or CleanConfig()

    # 1. Normalise the historical characters.
    blocks: list[TextBlock] = []
    for page in pages:
        for block in page.blocks:
            blocks.append(block.with_lines(tuple(normalize_line(line) for line in block.lines)))

    # 2. Mark the footnotes before anything else: a numbered note at the
    #    bottom of the page must not be mistaken for a repeated running head.
    blocks, detected_footnotes = _detect_footnotes(blocks, config)

    # 3. Find the blocks that repeat from page to page.
    per_page: dict[int, list[TextBlock]] = {}
    for block in blocks:
        per_page.setdefault(block.page, []).append(block)
    repeated, repeated_texts = _find_repeated_blocks(
        [PageContent(index=index, blocks=tuple(items)) for index, items in per_page.items()],
        config,
    )

    removed_page_numbers = 0
    kept: list[TextBlock] = []
    removed_folio_keys: set[str] = set()
    for block in blocks:
        text = " ".join(block.text.split())
        only_block = len(per_page.get(block.page, ())) == 1
        if (
            not only_block
            and _PAGE_NUMBER_RE.match(text)
            and _is_running_head_candidate(block, config)
        ):
            removed_page_numbers += 1
            removed_folio_keys.add(folded(text))
            continue
        if not only_block and (block.page, block.order) in repeated:
            continue
        kept.append(block)

    running_heads = tuple(
        sorted(text for text in repeated_texts if folded(text) not in removed_folio_keys)
    )

    # 4. Mark the headings before the paragraphs are built.
    kept = _mark_headings(kept)

    # 4. Gather the lines that belong to the same paragraph.
    kept, merged_paragraphs, hyphen_joins = _merge_into_paragraphs(kept)

    # 5. Repair the words broken at the end of a line.
    joined_hyphens = hyphen_joins
    repaired: list[TextBlock] = []
    for block in kept:
        lines, joins = _join_hyphenated_lines(block.lines)
        joined_hyphens += joins
        repaired.append(block.with_lines(lines) if joins else block)

    # 6. Redistribute the blocks over the pages.
    grouped: dict[int, list[TextBlock]] = {}
    for block in repaired:
        grouped.setdefault(block.page, []).append(block)
    cleaned_pages = tuple(
        PageContent(index=page.index, blocks=tuple(grouped.get(page.index, ()))) for page in pages
    )

    return CleanResult(
        pages=cleaned_pages,
        removed_running_heads=running_heads,
        removed_page_numbers=removed_page_numbers,
        joined_hyphens=joined_hyphens,
        merged_paragraphs=merged_paragraphs,
        detected_footnotes=detected_footnotes,
    )
