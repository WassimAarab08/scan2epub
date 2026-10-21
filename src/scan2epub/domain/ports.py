"""Ports of the hexagonal architecture.

A *port* is a protocol implemented by the infrastructure adapters. The
application layer only ever talks to these protocols, which is what makes the
OCR engine and the text corrector interchangeable.

Adding a new engine is a matter of implementing :class:`OcrEngine` and
registering it in ``config.toml`` — see ``docs/adding-an-engine.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from scan2epub.domain.models import (
    CorrectionResult,
    PageImage,
    PageLayout,
    TextBlock,
)

__all__ = [
    "Cache",
    "LayoutAnalyzer",
    "OcrEngine",
    "PagePreprocessor",
    "PageSource",
    "TextCorrector",
]


@runtime_checkable
class PageSource(Protocol):
    """Produces the rasterised pages of a source document."""

    def pages(self) -> list[PageImage]:
        """Return every page of the document, in reading order."""
        ...


@runtime_checkable
class PagePreprocessor(Protocol):
    """Cleans up a page image before it reaches the OCR engine."""

    def process(self, image: PageImage, out_dir: Path) -> PageImage:
        """Return a preprocessed copy of ``image`` written under ``out_dir``."""
        ...


@runtime_checkable
class LayoutAnalyzer(Protocol):
    """Finds the structural regions of a page."""

    def analyze(self, image: PageImage) -> PageLayout:
        """Return the layout of ``image``."""
        ...


@runtime_checkable
class OcrEngine(Protocol):
    """Recognises the text of a page image.

    This is the main extension point of the project. Implementations may be
    local (Tesseract, TeleOCR, PaddleOCR-VL, Kraken) or remote (any
    LiteLLM-supported vision model).
    """

    name: str

    def recognize(self, image: PageImage) -> list[TextBlock]:
        """Return the text blocks of ``image`` in reading order."""
        ...


@runtime_checkable
class TextCorrector(Protocol):
    """Repairs OCR mistakes in already recognised text.

    The corrector is *not* trusted: the application layer compares the result
    with the original and rejects corrections that drift too far away.
    """

    name: str

    def correct(self, blocks: Sequence[TextBlock]) -> CorrectionResult:
        """Return the corrected blocks together with the recorded diffs."""
        ...


@runtime_checkable
class Cache(Protocol):
    """A content-addressed store for pipeline artefacts."""

    def get(self, key: str) -> bytes | None:
        """Return the artefact stored under ``key``, or ``None``."""
        ...

    def put(self, key: str, data: bytes) -> None:
        """Store ``data`` under ``key``."""
        ...
