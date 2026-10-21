"""Tests for the deterministic cleaning stage."""

from __future__ import annotations

from scan2epub.application.stages.clean import clean_pages
from scan2epub.config import CleanConfig
from scan2epub.domain.models import BBox, BlockKind, PageContent, TextBlock


def _block(
    text: str,
    top: float,
    bottom: float,
    *,
    order: int,
    page: int,
    kind: BlockKind = BlockKind.BODY,
) -> TextBlock:
    """Build a text block with the given geometry."""
    return TextBlock(
        lines=tuple(text.split("\n")),
        bbox=BBox(0.1, top, 0.9, bottom),
        confidence=0.9,
        kind=kind,
        order=order,
        page=page,
    )


def test_running_heads_are_removed(pages: list[PageContent]) -> None:
    """A head that repeats on every page disappears."""
    result = clean_pages(pages)
    for page in result.pages:
        for block in page.blocks:
            assert "HISTORIA DE LA IMPRENTA" not in block.text
    assert "HISTORIA DE LA IMPRENTA" in result.removed_running_heads


def test_folios_are_removed(pages: list[PageContent]) -> None:
    """The page numbers disappear and are counted apart."""
    result = clean_pages(pages)
    assert result.removed_page_numbers == 3
    for page in result.pages:
        for block in page.blocks:
            assert "42" not in block.text


def test_folios_are_not_reported_as_running_heads(pages: list[PageContent]) -> None:
    """The page numbers are not listed as running heads."""
    result = clean_pages(pages)
    assert "— 42 —" not in result.removed_running_heads


def test_a_block_that_repeats_only_once_is_kept() -> None:
    """A short line that appears on a single page is content, not a head."""
    pages = [
        PageContent(
            index=0,
            blocks=(
                _block("UNICO", 0.02, 0.05, order=0, page=0),
                _block("Cuerpo del texto.", 0.2, 0.3, order=1, page=0),
            ),
        )
    ]
    result = clean_pages(pages)
    assert "UNICO" in result.pages[0].blocks[0].text


def test_the_only_block_of_a_page_is_never_removed() -> None:
    """A page with a single block keeps it, even in the header zone."""
    pages = [
        PageContent(
            index=0,
            blocks=(_block("HISTORIA DE LA IMPRENTA", 0.02, 0.05, order=0, page=0),),
        )
    ]
    result = clean_pages(pages)
    assert len(result.pages[0].blocks) == 1


def test_hyphenated_words_are_rejoined() -> None:
    """A word broken at the end of a line is glued back together."""
    pages = [
        PageContent(
            index=0,
            blocks=(_block("una gran im-\nprenta de Madrid", 0.2, 0.3, order=0, page=0),),
        )
    ]
    result = clean_pages(pages)
    assert "imprenta" in result.pages[0].blocks[0].text
    assert result.joined_hyphens == 1


def test_a_dash_is_not_treated_as_a_hyphenation() -> None:
    """A spaced dash keeps the two words apart."""
    pages = [
        PageContent(
            index=0,
            blocks=(_block("palabra -\ncontinua", 0.2, 0.3, order=0, page=0),),
        )
    ]
    result = clean_pages(pages)
    assert result.joined_hyphens == 0
    assert "-" in result.pages[0].blocks[0].text


def test_lines_of_the_same_paragraph_are_merged() -> None:
    """The lines that do not close a sentence are gathered together."""
    pages = [
        PageContent(
            index=0,
            blocks=(
                _block("El hombre que escribe con la letra larga", 0.2, 0.24, order=0, page=0),
                _block("llamada por los impresores de Madrid.", 0.25, 0.29, order=1, page=0),
            ),
        )
    ]
    result = clean_pages(pages)
    assert len(result.pages[0].blocks) == 1
    assert result.merged_paragraphs == 1
    assert "impresores de Madrid." in result.pages[0].blocks[0].text


def test_paragraphs_that_continue_on_the_next_page_are_merged() -> None:
    """A sentence split by a page break becomes a single paragraph."""
    pages = [
        PageContent(
            index=0,
            blocks=(_block("la imprenta de Madrid y sus costes", 0.2, 0.3, order=0, page=0),),
        ),
        PageContent(
            index=1,
            blocks=(_block("fueron muy altos en aquel tiempo.", 0.2, 0.3, order=0, page=1),),
        ),
    ]
    result = clean_pages(pages)
    assert len(result.pages[0].blocks) == 1
    assert "muy altos en aquel tiempo." in result.pages[0].blocks[0].text


def test_a_footnote_does_not_break_a_paragraph() -> None:
    """A note at the bottom of a page does not interrupt the text."""
    pages = [
        PageContent(
            index=0,
            blocks=(
                _block("la imprenta de Madrid y sus", 0.2, 0.3, order=0, page=0),
                _block("1 Nota del autor.", 0.85, 0.88, order=1, page=0),
            ),
        ),
        PageContent(
            index=1,
            blocks=(_block("costes fueron muy altos.", 0.2, 0.3, order=0, page=1),),
        ),
    ]
    result = clean_pages(pages)
    assert result.detected_footnotes == 1
    body = [b for b in result.pages[0].blocks if b.kind is BlockKind.BODY]
    assert len(body) == 1
    assert "costes fueron muy altos." in body[0].text


def test_footnotes_are_detected(pages: list[PageContent]) -> None:
    """A numbered note at the bottom of the page is marked as a footnote."""
    result = clean_pages(pages)
    kinds = [block.kind for page in result.pages for block in page.blocks]
    assert BlockKind.FOOTNOTE in kinds


def test_long_s_is_normalised(pages: list[PageContent]) -> None:
    """The long s becomes a plain s during the cleaning."""
    pages = [
        PageContent(
            index=0,
            blocks=(_block("el eſtado de la caſa", 0.2, 0.3, order=0, page=0),),
        )
    ]
    result = clean_pages(pages)
    assert result.pages[0].blocks[0].text == "el estado de la casa"


def test_the_cleaning_is_deterministic(pages: list[PageContent]) -> None:
    """Running the cleaner twice gives the same result."""
    first = clean_pages(pages)
    second = clean_pages(pages)
    assert first.pages == second.pages


def test_a_heading_is_not_merged_with_the_body() -> None:
    """A heading always ends a paragraph."""
    pages = [
        PageContent(
            index=0,
            blocks=(
                _block("CAPITULO PRIMERO", 0.12, 0.16, order=0, page=0),
                _block("El texto empieza aqui", 0.2, 0.24, order=1, page=0),
            ),
        )
    ]
    result = clean_pages(pages)
    assert len(result.pages[0].blocks) == 2
    assert result.pages[0].blocks[0].kind is BlockKind.HEADING


def test_the_config_controls_the_number_of_repetitions() -> None:
    """A head that appears twice is kept by default and removed on demand."""
    pages = [
        PageContent(
            index=index,
            blocks=(
                _block("HISTORIA DE LA IMPRENTA", 0.02, 0.05, order=0, page=index),
                _block("Cuerpo.", 0.2, 0.3, order=1, page=index),
            ),
        )
        for index in range(2)
    ]
    default = clean_pages(pages, CleanConfig())
    assert "HISTORIA DE LA IMPRENTA" in default.pages[0].blocks[0].text

    strict = clean_pages(pages, CleanConfig(min_running_head_repeats=2))
    assert "HISTORIA DE LA IMPRENTA" not in strict.pages[0].blocks[0].text
