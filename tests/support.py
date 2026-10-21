"""Helpers shared by the test suite."""

from __future__ import annotations

import re

__all__ = ["strip_ansi"]

#: The escape sequences of the terminal colours.
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-B]")


def strip_ansi(text: str) -> str:
    """Return the text without the escape sequences of the terminal.

    The output of Rich is coloured when the terminal supports it, so a test
    that parses it as JSON has to remove the colours first.
    """
    return _ANSI_RE.sub("", text)
