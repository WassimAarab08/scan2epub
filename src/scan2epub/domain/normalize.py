"""Deterministic normalisation of historical typographic characters.

Scanned books from the 18th and 19th centuries use characters that either do
not exist in modern Unicode or that modern readers render badly. This module
implements the *safe*, purely mechanical fixes:

* the long s (``ſ``) becomes a plain ``s``;
* the Latin ligatures (``ﬁ``, ``ﬂ``, ``ﬃ``, ``ﬄ``, ``ﬅ``…) are expanded;
* soft hyphens, zero-width spaces and exotic spaces are removed or folded;
* hyphen-like dashes are folded to the ASCII hyphen so that the
  end-of-line hyphenation repair can recognise them.

Nothing here changes spelling, grammar or wording. That is the job of the
optional LLM corrector, which is guarded by an edit-distance limit.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "LIGATURE_MAP",
    "expand_ligatures",
    "normalize_line",
    "normalize_text",
    "normalize_whitespace",
    "strip_control_characters",
]

#: Latin ligatures and their ASCII expansion.
LIGATURE_MAP: dict[str, str] = {
    "\ufb00": "ff",  # ﬀ
    "\ufb01": "fi",  # ﬁ
    "\ufb02": "fl",  # ﬂ
    "\ufb03": "ffi",  # ﬃ
    "\ufb04": "ffl",  # ﬄ
    "\ufb05": "st",  # ﬅ
    "\ufb06": "st",  # ﬆ
}

#: Characters that behave like a plain space.
_SPACE_LIKE: frozenset[str] = frozenset(
    {
        "\u00a0",  # no-break space
        "\u1680",  # ogham space mark
        "\u2000",  # en quad
        "\u2001",  # em quad
        "\u2002",  # en space
        "\u2003",  # em space
        "\u2004",  # three-per-em space
        "\u2005",  # four-per-em space
        "\u2006",  # six-per-em space
        "\u2007",  # figure space
        "\u2008",  # punctuation space
        "\u2009",  # thin space
        "\u200a",  # hair space
        "\u202f",  # narrow no-break space
        "\u205f",  # medium mathematical space
        "\u3000",  # ideographic space
    }
)

#: Characters that carry no meaning and must simply disappear.
_INVISIBLE: frozenset[str] = frozenset(
    {
        "\u00ad",  # soft hyphen
        "\u200b",  # zero width space
        "\u200c",  # zero width non-joiner
        "\u200d",  # zero width joiner
        "\u2060",  # word joiner
        "\ufeff",  # zero width no-break space / BOM
    }
)

#: Dash-like characters that must be treated as a plain hyphen.
_HYPHEN_LIKE: frozenset[str] = frozenset({"\u2010", "\u2011", "\u2012", "\u2212"})

#: Typographic quotes and dashes that are kept as they are.
_PRESERVED: frozenset[str] = frozenset(
    {
        "\u2013",  # en dash
        "\u2014",  # em dash
        "\u2015",  # horizontal bar
        "\u2018",  # left single quotation mark
        "\u2019",  # right single quotation mark
        "\u201c",  # left double quotation mark
        "\u201d",  # right double quotation mark
        "\u00ab",  # left guillemet
        "\u00bb",  # right guillemet
        "\u00a1",  # inverted exclamation mark
        "\u00bf",  # inverted question mark
    }
)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def strip_control_characters(text: str) -> str:
    """Remove control characters that must never reach the EPUB."""
    return _CONTROL_RE.sub("", text)


def normalize_whitespace(text: str) -> str:
    """Fold exotic spaces, drop invisible characters and squeeze runs of blanks."""
    chars: list[str] = []
    for char in text:
        if char in _INVISIBLE:
            continue
        if char in _SPACE_LIKE:
            chars.append(" ")
            continue
        if char in _HYPHEN_LIKE:
            chars.append("-")
            continue
        chars.append(char)
    return _MULTI_SPACE_RE.sub(" ", "".join(chars))


def expand_ligatures(text: str) -> str:
    """Expand the Latin ligatures and the long s into plain ASCII letters."""
    if "ſ" not in text and not any(lig in text for lig in LIGATURE_MAP):
        return text
    out = text.replace("ſ", "s")
    for ligature, expansion in LIGATURE_MAP.items():
        out = out.replace(ligature, expansion)
    return out


def normalize_line(line: str) -> str:
    """Normalise a single physical line of text."""
    if not line:
        return ""
    normalized = expand_ligatures(line)
    normalized = normalize_whitespace(normalized)
    normalized = strip_control_characters(normalized)
    return normalized.strip()


def normalize_text(text: str) -> str:
    """Normalise a whole block of text, line by line.

    Line structure is preserved because the end-of-line hyphenation repair
    depends on it.
    """
    if not text:
        return ""
    lines = [normalize_line(line) for line in text.split("\n")]
    return "\n".join(lines)


def is_ligature_free(text: str) -> bool:
    """Whether ``text`` contains no long s and no Latin ligature."""
    return "ſ" not in text and not any(lig in text for lig in LIGATURE_MAP)


def folded(text: str) -> str:
    """Return a comparison key used to detect repeated running heads."""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower()
    # Fold every run of digits to a single placeholder so that "— 12 —" and
    # "— 13 —" compare equal.
    normalized = re.sub(r"\d+", "#", normalized)
    normalized = re.sub(r"[^\w#]+", " ", normalized)
    return " ".join(normalized.split())
