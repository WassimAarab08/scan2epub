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
#: A word continuation after a hyphen always starts with a lowercase letter.
#: The accented characters are written as escapes so that the source of the
#: file stays ASCII and the character class holds no duplicate.
_CONTINUATION_RE = re.compile(
    "^[a-z"
    "\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f1\u00e7"  # a e i o u n c
    "\u00e0\u00e8\u00ec\u00f2\u00f9"  # grave
    "\u00e2\u00ea\u00ee\u00f4\u00fb"  # circumflex
    "\u00e4\u00eb\u00ef\u00f6\u00e3\u00f5"  # umlaut and tilde
    "\u00e6\u0153\u00df]"  # ae oe sharp s
)

#: A conjunction at the end of a line. The word must stand on its own: the
#: English word "company" does not end with a conjunction.
_TRAILING_CONJUNCTION_RE = re.compile(
    r"(?:\W|^)(?:y|e|o|u|i|ni|y|a|and|or|but|so|that|which|when|where)$",
    re.IGNORECASE,
)


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


def _footnote_key(text: str) -> str:
    """Return the comparison key of a footnote.

    Unlike a running head, a footnote is compared verbatim: the number of
    the note is part of its identity, so two notes with a different number
    are not the same note.
    """
    return " ".join(text.lower().split())


def _find_repeated_footnotes(blocks: list[TextBlock], config: CleanConfig) -> set[tuple[int, int]]:
    """Return the footnotes that are repeated verbatim on many pages.

    A real note belongs to the page it is printed on. The very same note,
    with the very same number, on three pages or more is boilerplate — a
    footer that happens to start with a number.
    """
    occurrences: dict[str, list[tuple[int, int]]] = {}
    for block in blocks:
        if block.kind is not BlockKind.FOOTNOTE:
            continue
        key = _footnote_key(block.text)
        if not key:
            continue
        occurrences.setdefault(key, []).append((block.page, block.order))

    repeated: set[tuple[int, int]] = set()
    for positions in occurrences.values():
        distinct_pages = {page_index for page_index, _ in positions}
        if len(distinct_pages) >= config.min_running_head_repeats:
            repeated.update(positions)
    return repeated


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
    if following[:1].isupper() and following[:1].isascii():
        # An upper-case start usually means a new sentence, unless the
        # previous line ends with a conjunction or a comma.
        stripped = previous.rstrip()
        return stripped.endswith((",", ";", ":")) or bool(_TRAILING_CONJUNCTION_RE.search(stripped))
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
    last_footnote: int | None = None
    merges = 0
    hyphen_joins = 0
    for block in blocks:
        if block.kind is BlockKind.HEADING:
            merged.append(block)
            last_body = None
            last_footnote = None
            continue
        if block.kind is BlockKind.FOOTNOTE:
            # A note that the OCR split in two is a single note: the second
            # half carries no marker of its own.
            if last_footnote is not None:
                previous = merged[last_footnote]
                previous_text = " ".join(previous.text.split())
                current_text = " ".join(block.text.split())
                if _FOOTNOTE_RE.match(current_text) is None and _continues_previous(
                    previous_text, current_text
                ):
                    merged[last_footnote] = previous.with_lines(previous.lines + block.lines)
                    merges += 1
                    continue
            merged.append(block)
            last_footnote = len(merged) - 1
            continue
        if block.kind is not BlockKind.BODY:
            # Illustrations and other kinds do not break the paragraph.
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
        last_footnote = None
    return merged, merges, hyphen_joins


def _detect_footnotes(blocks: list[TextBlock], config: CleanConfig) -> tuple[list[TextBlock], int]:
    """Mark the blocks that look like footnotes.

    A note that the OCR split in two has a marker only in its first half, so
    the halves are recognised together: the second one continues the note.
    """
    detected = 0
    marked: list[TextBlock] = []
    last_footnote: int | None = None
    for block in blocks:
        candidate = block
        if candidate.kind is BlockKind.BODY and candidate.bbox.y0 >= config.footnote_zone:
            text = " ".join(candidate.text.split())
            has_marker = _FOOTNOTE_RE.match(text) is not None
            continues = False
            if last_footnote is not None and not has_marker:
                previous = marked[last_footnote]
                previous_text = " ".join(previous.text.split())
                continues = _continues_previous(previous_text, text)
            if has_marker or continues:
                candidate = candidate.with_kind(BlockKind.FOOTNOTE)
                detected += 1
                last_footnote = len(marked)
        else:
            last_footnote = None
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
    repeated_footnotes = _find_repeated_footnotes(blocks, config)

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
        if not only_block and (block.page, block.order) in repeated_footnotes:
            # The very same note on many pages is boilerplate, not a note.
            removed_folio_keys.add(_footnote_key(text))
            continue
        kept.append(block)

    running_heads = tuple(
        sorted(
            text
            for text in repeated_texts
            if folded(text) not in removed_folio_keys
            and _footnote_key(text) not in removed_folio_keys
        )
    )

    # 4. Mark the headings before the paragraphs are built.
    kept = _mark_headings(kept)

    # 5. Gather the lines that belong to the same paragraph.
    kept, merged_paragraphs, hyphen_joins = _merge_into_paragraphs(kept)

    # 6. Repair the words broken at the end of a line.
    joined_hyphens = hyphen_joins
    repaired: list[TextBlock] = []
    for block in kept:
        lines, joins = _join_hyphenated_lines(block.lines)
        joined_hyphens += joins
        repaired.append(block.with_lines(lines) if joins else block)

    # 7. Redistribute the blocks over the pages.
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
