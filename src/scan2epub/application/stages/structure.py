"""Book structure: headings, chapters and the table of contents.

The stage turns a flat list of recognised blocks into a structured book. It
never invents content: a block becomes a heading only when several
independent signals agree (length, position, alignment, capitalisation or a
known structural keyword).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from scan2epub.application.stages.headings import classify_heading, classify_page
from scan2epub.domain.models import (
    BlockKind,
    Book,
    BookMetadata,
    Chapter,
    PageContent,
    TextBlock,
)

__all__ = ["classify_heading", "structure_book"]


def _classify_blocks(pages: Sequence[PageContent]) -> list[TextBlock]:
    """Flatten the pages and mark the heading blocks.

    The blocks of a page are classified together, because the typography of
    the page (a title set in a bigger type than the body) is one of the
    signals.
    """
    blocks: list[TextBlock] = []
    for page in pages:
        levels = classify_page(page.blocks)
        for block, level in zip(page.blocks, levels, strict=True):
            candidate = block
            if level is None:
                blocks.append(candidate)
                continue
            if candidate.kind is BlockKind.BODY:
                candidate = candidate.with_kind(BlockKind.HEADING).with_level(level)
            elif candidate.kind is BlockKind.HEADING and candidate.level == 0:
                candidate = candidate.with_level(level)
            blocks.append(candidate)
    return blocks


def _promote_the_title(blocks: list[TextBlock]) -> list[TextBlock]:
    """Make sure that the book has a chapter-level heading.

    A book whose headings were all taken as sections would end up as a
    single chapter. The first heading is the title of the book, so it is
    promoted to the chapter level.
    """
    if any(block.kind is BlockKind.HEADING and block.level == 1 for block in blocks):
        return blocks
    for index, block in enumerate(blocks):
        if block.kind is BlockKind.HEADING:
            promoted = list(blocks)
            promoted[index] = block.with_level(1)
            return promoted
    return blocks


def structure_book(
    pages: Sequence[PageContent],
    metadata: BookMetadata,
    *,
    front_matter_title: str | None = None,
) -> Book:
    """Group the recognised blocks into chapters.

    Args:
        pages: The cleaned pages.
        metadata: The metadata of the book.
        front_matter_title: The title given to the content that precedes the
            first chapter. When omitted, the content is attached to the first
            chapter.

    Returns:
        The structured book.
    """
    blocks = _promote_the_title(_classify_blocks(pages))

    if not metadata.title.strip():
        # The book titles itself: the first heading of the document is the
        # title that the printer set, and the caller left the field empty.
        first_heading = next((block for block in blocks if block.kind is BlockKind.HEADING), None)
        if first_heading is not None:
            metadata = replace(metadata, title=" ".join(first_heading.text.split()))

    chapter_starts: list[int] = [
        index
        for index, block in enumerate(blocks)
        if block.kind is BlockKind.HEADING and block.level == 1
    ]

    chapters: list[Chapter] = []
    if not chapter_starts:
        chapters.append(
            Chapter(
                id="chapter-1",
                title=metadata.title,
                level=1,
                start_page=blocks[0].page if blocks else 0,
                end_page=blocks[-1].page if blocks else 0,
                blocks=tuple(blocks),
            )
        )
    else:
        if chapter_starts[0] > 0:
            front = blocks[: chapter_starts[0]]
            title = front_matter_title or metadata.title
            chapters.append(
                Chapter(
                    id="front-matter",
                    title=title,
                    level=1,
                    start_page=front[0].page,
                    end_page=front[-1].page,
                    blocks=tuple(front),
                )
            )
        for position, start in enumerate(chapter_starts):
            end = (
                chapter_starts[position + 1] if position + 1 < len(chapter_starts) else len(blocks)
            )
            title_block = blocks[start]
            body = blocks[start + 1 : end]
            title = " ".join(title_block.text.split()) or metadata.title
            chapters.append(
                Chapter(
                    id=f"chapter-{position + 1}",
                    title=title,
                    level=1,
                    start_page=title_block.page,
                    end_page=body[-1].page if body else title_block.page,
                    blocks=tuple(body),
                )
            )

    return Book(
        metadata=metadata,
        chapters=tuple(chapters),
        figures=(),
        pages=tuple(pages),
    )
