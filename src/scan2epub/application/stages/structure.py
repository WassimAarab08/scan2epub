"""Book structure: headings, chapters and the table of contents.

The stage turns a flat list of recognised blocks into a structured book. It
never invents content: a block becomes a heading only when several
independent signals agree (length, position, alignment, capitalisation or a
known structural keyword).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from scan2epub.application.stages.headings import classify_heading
from scan2epub.domain.models import (
    BlockKind,
    Book,
    BookMetadata,
    Chapter,
    PageContent,
    TextBlock,
)

__all__ = ["StructureResult", "classify_heading", "structure_book"]


@dataclass(frozen=True, slots=True)
class StructureResult:
    """The outcome of the structuring pass."""

    book: Book
    headings: int = 0
    chapters: int = 0


def _classify_blocks(pages: Sequence[PageContent]) -> list[TextBlock]:
    """Flatten the pages and mark the heading blocks."""
    blocks: list[TextBlock] = []
    for page in pages:
        for block in page.blocks:
            candidate = block
            if candidate.kind is BlockKind.BODY:
                detected = classify_heading(candidate)
                if detected is not None:
                    candidate = candidate.with_kind(BlockKind.HEADING).with_level(detected)
            elif candidate.kind is BlockKind.HEADING and candidate.level == 0:
                detected = classify_heading(candidate)
                if detected is not None:
                    candidate = candidate.with_level(detected)
            blocks.append(candidate)
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
    blocks = _classify_blocks(pages)

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
