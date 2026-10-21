"""Extra tests for the heading detection edge cases."""

from __future__ import annotations

from scan2epub.application.stages.headings import classify_heading, is_heading_text
from scan2epub.domain.models import BBox, TextBlock


def _block(text: str, bbox: BBox | None = None) -> TextBlock:
    """Build a text block with the given geometry."""
    return TextBlock(
        lines=(text,),
        bbox=bbox or BBox(0.1, 0.2, 0.9, 0.24),
        confidence=0.9,
    )


def test_an_empty_block_is_not_a_heading() -> None:
    """A block without text is never a heading."""
    assert classify_heading(_block("   ")) is None


def test_a_long_all_capitals_line_is_a_heading() -> None:
    """An all-capitals line is a heading even when it is long."""
    text = "ESTA ES UNA FRASE MUY LARGA QUE NO FUNCIONA COMO TITULO"
    assert classify_heading(_block(text)) == 2


def test_a_shouted_sentence_is_not_a_heading() -> None:
    """An all-capitals sentence with a full stop is not a heading."""
    text = "ESTA FRASE MUY LARGA NO FUNCIONA COMO TITULO, Y ADEMAS ES MAS LARGA."
    assert classify_heading(_block(text)) is None


def test_a_short_all_capitals_line_with_a_full_stop_is_a_heading() -> None:
    """A short all-capitals line is a heading even with a full stop."""
    assert classify_heading(_block("EL NIÑO PERDIDO.")) == 2


def test_a_centred_line_that_is_too_wide_is_not_a_heading() -> None:
    """A line that fills the page is body text."""
    block = _block("De la antigüedad de las letras", BBox(0.05, 0.1, 0.95, 0.14))
    assert classify_heading(block) is None


def test_a_centred_arabic_numeral_is_a_heading() -> None:
    """A centred number is a section heading."""
    block = _block("12", BBox(0.45, 0.1, 0.55, 0.14))
    assert classify_heading(block) == 2


def test_an_arabic_numeral_that_is_not_centred_is_not_a_heading() -> None:
    """A number at the left margin is body text."""
    block = _block("12", BBox(0.1, 0.1, 0.15, 0.14))
    assert classify_heading(block) is None


def test_the_text_only_helper_agrees_with_the_geometric_one() -> None:
    """``is_heading_text`` recognises the same words."""
    assert is_heading_text("CAPITULO PRIMERO")
    assert is_heading_text("IV")
    assert not is_heading_text("El hombre que escribe con la letra larga.")


def test_the_text_only_helper_rejects_long_lines() -> None:
    """A long line is not a heading."""
    assert not is_heading_text("palabra " * 30)
