"""Tests for the character normalisation helpers."""

from __future__ import annotations

import pytest

from scan2epub.domain.normalize import (
    expand_ligatures,
    folded,
    normalize_line,
    normalize_text,
    normalize_whitespace,
    strip_control_characters,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("la caſa", "la casa"),
        ("eſtado", "estado"),
        ("ſi", "si"),
        ("eſta", "esta"),
        ("ſſ", "ss"),
    ],
)
def test_long_s_is_normalised(raw: str, expected: str) -> None:
    """The long s becomes a plain s."""
    assert normalize_line(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ﬁ", "fi"),
        ("ﬂ", "fl"),
        ("ﬀ", "ff"),
        ("ﬃ", "ffi"),
        ("ﬄ", "ffl"),
        ("ﬅ", "st"),
        ("ﬆ", "st"),
    ],
)
def test_ligatures_are_expanded(raw: str, expected: str) -> None:
    """The Latin ligatures are expanded into plain letters."""
    assert expand_ligatures(raw) == expected


def test_soft_hyphen_and_zero_width_space_are_removed() -> None:
    """Invisible characters never reach the EPUB."""
    assert normalize_line("im\u00adprenta") == "imprenta"
    assert normalize_line("casa\u200b") == "casa"


def test_exotic_spaces_become_plain_spaces() -> None:
    """Every kind of space is folded into an ASCII space."""
    assert normalize_line("uno\u00a0dos\u2009tres") == "uno dos tres"


def test_runs_of_blanks_are_squeezed() -> None:
    """Two spaces become one."""
    assert normalize_line("uno   dos") == "uno dos"


def test_hyphen_like_dashes_are_folded() -> None:
    """The dash variants are recognised as a plain hyphen."""
    assert normalize_line("im\u2010prenta") == "im-prenta"


def test_control_characters_are_stripped() -> None:
    """Control characters are removed."""
    assert strip_control_characters("a\x00b\x07c") == "abc"


def test_normalize_text_keeps_the_line_structure() -> None:
    """The line breaks survive the normalisation."""
    result = normalize_text("la ſe\nma\u00a0linea")
    assert result == "la se\nma linea"


def test_normalize_line_keeps_typographic_quotes() -> None:
    """Curly quotes and dashes are left alone."""
    assert normalize_line("\u00abCita\u00bb \u2014 dijo") == "\u00abCita\u00bb \u2014 dijo"


def test_folded_compares_running_heads() -> None:
    """The comparison key ignores the digits and the punctuation."""
    assert folded("— 42 —") == folded("— 137 —")
    assert folded("HISTORIA DE LA IMPRENTA") == folded("Historia  de  la  imprenta")


def test_folded_is_case_insensitive() -> None:
    """The comparison key ignores the case."""
    assert folded("El Niño") == folded("el nino")


def test_normalize_whitespace_is_idempotent() -> None:
    """Normalising twice does not change anything."""
    once = normalize_whitespace("a\u00a0\u2009 b")
    assert normalize_whitespace(once) == once
