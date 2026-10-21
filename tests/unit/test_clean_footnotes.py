"""Tests for the repeated footnotes."""

from __future__ import annotations

from scan2epub.application.stages.clean import clean_pages
from scan2epub.config import CleanConfig
from scan2epub.domain.models import BBox, BlockKind, PageContent, TextBlock


def _note(page: int, order: int, text: str = "1 Nota del autor.") -> TextBlock:
    """Build a footnote at the bottom of a page."""
    return TextBlock(
        lines=(text,),
        bbox=BBox(0.1, 0.86, 0.9, 0.9),
        confidence=0.9,
        kind=BlockKind.BODY,
        order=order,
        page=page,
    )


def _body(page: int, order: int, text: str) -> TextBlock:
    """Build a body paragraph."""
    return TextBlock(
        lines=(text,),
        bbox=BBox(0.1, 0.2, 0.9, 0.3),
        confidence=0.9,
        kind=BlockKind.BODY,
        order=order,
        page=page,
    )


def test_a_note_repeated_on_every_page_is_boilerplate() -> None:
    """The very same note on three pages is not a real note."""
    pages = [
        PageContent(
            index=index,
            blocks=(
                _body(index, 0, f"Texto de la pagina {index}."),
                _note(index, 1),
            ),
        )
        for index in range(3)
    ]
    result = clean_pages(pages, CleanConfig(min_running_head_repeats=3))
    for page in result.pages:
        assert all(block.kind is not BlockKind.FOOTNOTE for block in page.blocks)


def test_a_note_that_differs_on_every_page_is_kept() -> None:
    """A different note on each page is real content."""
    pages = [
        PageContent(
            index=index,
            blocks=(
                _body(index, 0, f"Texto de la pagina {index}."),
                _note(index, 1, f"{index + 1} Nota numero {index + 1}."),
            ),
        )
        for index in range(3)
    ]
    result = clean_pages(pages, CleanConfig(min_running_head_repeats=3))
    footnotes = [
        block for page in result.pages for block in page.blocks if block.kind is BlockKind.FOOTNOTE
    ]
    assert len(footnotes) == 3


def test_a_note_that_appears_twice_is_kept() -> None:
    """Two pages are not enough to call a note boilerplate."""
    pages = [
        PageContent(
            index=index,
            blocks=(
                _body(index, 0, f"Texto de la pagina {index}."),
                _note(index, 1),
            ),
        )
        for index in range(2)
    ]
    result = clean_pages(pages, CleanConfig(min_running_head_repeats=3))
    footnotes = [
        block for page in result.pages for block in page.blocks if block.kind is BlockKind.FOOTNOTE
    ]
    assert len(footnotes) == 2
