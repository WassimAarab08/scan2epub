"""Tests for the heading detection and the book structuring."""

from __future__ import annotations

from scan2epub.application.stages.headings import classify_heading
from scan2epub.application.stages.structure import structure_book
from scan2epub.domain.models import (
    BBox,
    BlockKind,
    BookMetadata,
    PageContent,
    TextBlock,
)


def _block(
    text: str,
    *,
    top: float = 0.2,
    bottom: float = 0.24,
    order: int = 0,
    page: int = 0,
    kind: BlockKind = BlockKind.BODY,
    level: int = 0,
) -> TextBlock:
    """Build a text block with the given geometry."""
    return TextBlock(
        lines=tuple(text.split("\n")),
        bbox=BBox(0.1, top, 0.9, bottom),
        confidence=0.9,
        kind=kind,
        order=order,
        page=page,
        level=level,
    )


def test_a_structural_keyword_makes_a_level_one_heading() -> None:
    """``CAPITULO`` introduces a chapter."""
    assert classify_heading(_block("CAPITULO PRIMERO")) == 1
    assert classify_heading(_block("Libro segundo")) == 1
    assert classify_heading(_block("Chapter IV")) == 1


def test_a_roman_numeral_makes_a_level_two_heading() -> None:
    """A bare Roman numeral is a section heading."""
    assert classify_heading(_block("IV")) == 2


def test_an_all_capitals_line_is_a_heading() -> None:
    """An all-capitals line is a section heading."""
    assert classify_heading(_block("DE LA ANTIGUEDAD DE LAS LETRAS")) == 2


def test_ordinary_sentences_are_not_headings() -> None:
    """A body paragraph is not a heading."""
    assert classify_heading(_block("El hombre que escribe con la letra larga.")) is None


def test_a_long_line_is_not_a_heading() -> None:
    """A heading is short by definition."""
    assert classify_heading(_block("palabra " * 30)) is None


def test_a_centred_short_line_in_the_upper_half_is_a_heading() -> None:
    """A centred title is a heading."""
    block = TextBlock(
        lines=("De la antigüedad",),
        bbox=BBox(0.3, 0.1, 0.7, 0.14),
        confidence=0.9,
    )
    assert classify_heading(block) == 2


def test_a_centred_line_in_the_lower_half_is_not_a_heading() -> None:
    """A centred line at the bottom of the page is not a heading."""
    block = TextBlock(
        lines=("De la antigüedad",),
        bbox=BBox(0.3, 0.7, 0.7, 0.74),
        confidence=0.9,
    )
    assert classify_heading(block) is None


def test_the_book_is_split_into_chapters() -> None:
    """Each level-one heading starts a new chapter."""
    pages = [
        PageContent(
            index=0,
            blocks=(
                _block("CAPITULO PRIMERO", top=0.1, bottom=0.15, order=0, page=0),
                _block("Texto del primer capitulo.", order=1, page=0),
                _block("CAPITULO SEGUNDO", top=0.1, bottom=0.15, order=2, page=0),
                _block("Texto del segundo capitulo.", order=3, page=0),
            ),
        )
    ]
    book = structure_book(pages, BookMetadata(title="Libro"))
    assert [chapter.title for chapter in book.chapters] == [
        "CAPITULO PRIMERO",
        "CAPITULO SEGUNDO",
    ]
    assert book.chapters[0].blocks[0].text == "Texto del primer capitulo."


def test_a_book_without_headings_is_a_single_chapter() -> None:
    """Without headings the whole book is one document."""
    pages = [
        PageContent(
            index=0,
            blocks=(_block("Solo un parrafo de texto.", order=0, page=0),),
        )
    ]
    book = structure_book(pages, BookMetadata(title="Libro"))
    assert len(book.chapters) == 1
    assert book.chapters[0].title == "Libro"


def test_the_content_before_the_first_chapter_becomes_the_front_matter() -> None:
    """The text before the first heading is kept."""
    pages = [
        PageContent(
            index=0,
            blocks=(
                _block("Texto que precede al capitulo.", order=0, page=0),
                _block("CAPITULO PRIMERO", top=0.1, bottom=0.15, order=1, page=0),
                _block("Texto del capitulo.", order=2, page=0),
            ),
        )
    ]
    book = structure_book(pages, BookMetadata(title="Libro"))
    assert book.chapters[0].id == "front-matter"
    assert book.chapters[1].id == "chapter-1"


def test_the_page_range_of_a_chapter_is_recorded() -> None:
    """The start and end pages of every chapter are known."""
    pages = [
        PageContent(
            index=0,
            blocks=(
                _block("CAPITULO PRIMERO", top=0.1, bottom=0.15, order=0, page=0),
                _block("Texto.", order=1, page=0),
            ),
        ),
        PageContent(
            index=1,
            blocks=(
                _block("CAPITULO SEGUNDO", top=0.1, bottom=0.15, order=0, page=1),
                _block("Texto.", order=1, page=1),
            ),
        ),
    ]
    book = structure_book(pages, BookMetadata(title="Libro"))
    assert book.chapters[0].start_page == 0
    assert book.chapters[0].end_page == 0
    assert book.chapters[1].start_page == 1
