"""End-to-end tests of the conversion pipeline."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scan2epub.application.cache import FileCache
from scan2epub.application.pipeline import Pipeline
from scan2epub.config import Config, GeneralConfig
from scan2epub.domain.models import BookMetadata
from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
from scan2epub.infrastructure.ocr.tesseract import TesseractOcrEngine, tesseract_version
from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_tesseract() -> None:
    """The integration tests need the OCR engine."""
    if tesseract_version() is None:
        pytest.skip("Tesseract is not installed")


def _pipeline(
    source: Path,
    work_dir: Path,
    *,
    cache: FileCache | None = None,
    language: str = "eng",
    dpi: int = 150,
) -> Pipeline:
    """Build a pipeline that runs entirely locally."""
    config = Config(general=GeneralConfig(language=language, validate_epub=True))
    return Pipeline(
        source=PdfiumPageSource(source, dpi=dpi),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=TesseractOcrEngine(lang=language),
        config=config,
        work_dir=work_dir,
        cache=cache,
    )


class _CountingEngine:
    """An engine that counts how many times it is called."""

    name = "counting"

    def __init__(self, language: str = "eng") -> None:
        self.inner = TesseractOcrEngine(lang=language)
        self.calls = 0

    def recognize(self, image):
        """Recognise a page and count the call."""
        self.calls += 1
        return self.inner.recognize(image)


def test_a_pdf_is_converted_into_an_epub(sample_pdf: Path, tmp_path: Path) -> None:
    """The whole pipeline runs and produces a file."""
    output = tmp_path / "book.epub"
    pipeline = _pipeline(sample_pdf, tmp_path / "work")
    result = pipeline.run(BookMetadata(title="El libro", author="Anonimo"), output)

    assert output.is_file()
    assert output.stat().st_size > 0
    assert result.page_count == 3
    assert result.book.chapters


def test_the_epub_has_the_expected_structure(sample_pdf: Path, tmp_path: Path) -> None:
    """The container follows the EPUB 3 specification."""
    output = tmp_path / "book.epub"
    pipeline = _pipeline(sample_pdf, tmp_path / "work")
    pipeline.run(BookMetadata(title="El libro"), output)

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert names[0] == "mimetype"
        assert "META-INF/container.xml" in names
        assert "EPUB/package.opf" in names
        assert "EPUB/nav.xhtml" in names
        assert any(name.startswith("EPUB/text/") for name in names)


def test_the_running_head_and_the_folio_are_removed(sample_pdf: Path, tmp_path: Path) -> None:
    """The repeated furniture of the page does not reach the book."""
    output = tmp_path / "book.epub"
    pipeline = _pipeline(sample_pdf, tmp_path / "work")
    result = pipeline.run(BookMetadata(title="El libro"), output)

    assert "HISTORIA DE LA IMPRENTA" in result.clean.removed_running_heads
    assert result.clean.removed_page_numbers == 3

    with zipfile.ZipFile(output) as archive:
        document = "".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )
    assert "HISTORIA DE LA IMPRENTA" not in document


def test_the_hyphenated_words_are_rejoined(sample_pdf: Path, tmp_path: Path) -> None:
    """A word broken at the end of a line is glued back together."""
    output = tmp_path / "book.epub"
    pipeline = _pipeline(sample_pdf, tmp_path / "work")
    result = pipeline.run(BookMetadata(title="El libro"), output)
    assert result.clean.joined_hyphens >= 1

    with zipfile.ZipFile(output) as archive:
        document = archive.read("EPUB/text/chapter-001.xhtml").decode("utf-8")
    assert "imprenta de Madrid" in document


def test_the_text_is_merged_into_paragraphs(sample_pdf: Path, tmp_path: Path) -> None:
    """The printed lines become paragraphs."""
    output = tmp_path / "book.epub"
    pipeline = _pipeline(sample_pdf, tmp_path / "work")
    result = pipeline.run(BookMetadata(title="El libro"), output)
    assert result.clean.merged_paragraphs >= 3

    with zipfile.ZipFile(output) as archive:
        document = archive.read("EPUB/text/chapter-001.xhtml").decode("utf-8")
    assert document.count("<p") < 20


def test_the_cache_avoids_a_second_ocr_run(sample_pdf: Path, tmp_path: Path) -> None:
    """A second run reuses the cached recognition results."""
    cache = FileCache(tmp_path / "cache")
    output = tmp_path / "book.epub"
    config = Config(general=GeneralConfig(language="eng"))

    first = Pipeline(
        source=PdfiumPageSource(sample_pdf, dpi=150),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=_CountingEngine(),  # type: ignore[arg-type]
        config=config,
        work_dir=tmp_path / "work",
        cache=cache,
    )
    first.run(BookMetadata(title="El libro"), output)
    assert first.ocr.calls == 3  # type: ignore[attr-defined]

    second = Pipeline(
        source=PdfiumPageSource(sample_pdf, dpi=150),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=_CountingEngine(),  # type: ignore[arg-type]
        config=config,
        work_dir=tmp_path / "work",
        cache=cache,
    )
    second.run(BookMetadata(title="El libro"), output)
    assert second.ocr.calls == 0  # type: ignore[attr-defined]


def test_the_generated_epub_passes_the_validation(sample_pdf: Path, tmp_path: Path) -> None:
    """EPUBCheck accepts the generated file."""
    output = tmp_path / "book.epub"
    pipeline = _pipeline(sample_pdf, tmp_path / "work")
    result = pipeline.run(BookMetadata(title="El libro"), output)
    if not result.validation.ran:
        pytest.skip("EPUBCheck is not installed")
    assert result.validation.passed, result.validation.errors
    assert not result.validation.errors
