"""Tests for the ports of the hexagonal architecture.

The ports are the public extension points of the project. These tests check
that the protocols behave as advertised, so that a third party can rely on
them when writing a new engine.
"""

from __future__ import annotations

from pathlib import Path

from scan2epub.domain.models import (
    BBox,
    BlockKind,
    CorrectionResult,
    PageImage,
    PageLayout,
    TextBlock,
)
from scan2epub.domain.ports import (
    Cache,
    LayoutAnalyzer,
    OcrEngine,
    PagePreprocessor,
    PageSource,
    TextCorrector,
)


class _Engine:
    """A minimal OCR engine."""

    name = "demo"

    def recognize(self, image: PageImage) -> list[TextBlock]:
        """Return a single block."""
        return [TextBlock.from_text("hola", BBox(0.1, 0.1, 0.9, 0.2), page=image.index)]

    def describe(self) -> dict[str, object]:
        """Return the settings that change the result."""
        return {"engine": self.name, "lang": "demo"}


class _Corrector:
    """A minimal text corrector."""

    name = "demo"

    def correct(self, blocks: list[TextBlock]) -> CorrectionResult:
        """Return the blocks unchanged."""
        return CorrectionResult(blocks=tuple(blocks))


class _Source:
    """A minimal page source."""

    def pages(self) -> list[PageImage]:
        """Return a single page."""
        return [PageImage(index=0, path=Path("a.png"), width=10, height=10)]


class _Preprocessor:
    """A minimal pre-processor."""

    def process(self, image: PageImage, out_dir: Path) -> PageImage:
        """Return the page unchanged."""
        return image


class _Analyzer:
    """A minimal layout analyser."""

    def analyze(self, image: PageImage) -> PageLayout:
        """Return an empty layout."""
        return PageLayout(index=image.index)


class _Store:
    """A minimal cache."""

    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        """Return the artefact."""
        return self.items.get(key)

    def put(self, key: str, data: bytes) -> None:
        """Store the artefact."""
        self.items[key] = data


def test_an_engine_satisfies_the_ocr_port() -> None:
    """A class with the right methods satisfies the protocol."""
    assert isinstance(_Engine(), OcrEngine)


def test_a_corrector_satisfies_the_text_corrector_port() -> None:
    """A class with the right methods satisfies the protocol."""
    assert isinstance(_Corrector(), TextCorrector)


def test_a_source_satisfies_the_page_source_port() -> None:
    """A class with the right methods satisfies the protocol."""
    assert isinstance(_Source(), PageSource)


def test_a_preprocessor_satisfies_the_port() -> None:
    """A class with the right methods satisfies the protocol."""
    assert isinstance(_Preprocessor(), PagePreprocessor)


def test_an_analyzer_satisfies_the_port() -> None:
    """A class with the right methods satisfies the protocol."""
    assert isinstance(_Analyzer(), LayoutAnalyzer)


def test_a_store_satisfies_the_cache_port() -> None:
    """A class with the right methods satisfies the protocol."""
    assert isinstance(_Store(), Cache)


def test_a_class_without_the_methods_does_not_satisfy_the_port() -> None:
    """The protocols really discriminate."""

    class Empty:
        """A class that implements nothing."""

    assert not isinstance(Empty(), OcrEngine)
    assert not isinstance(Empty(), TextCorrector)
    assert not isinstance(Empty(), Cache)


def test_the_engine_port_returns_blocks_in_reading_order() -> None:
    """The engine returns the blocks of the page."""
    blocks = _Engine().recognize(PageImage(index=3, path=Path("a.png"), width=1, height=1))
    assert len(blocks) == 1
    assert blocks[0].text == "hola"
    assert blocks[0].kind is BlockKind.BODY
