"""Tests that prove the offline guarantee and the reproducibility."""

from __future__ import annotations

import socket
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


def _pipeline(source: Path, work: Path, **kwargs: object) -> Pipeline:
    """Build a local pipeline."""
    config = Config(general=GeneralConfig(language="eng", validate_epub=False))
    return Pipeline(
        source=PdfiumPageSource(source, dpi=150),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=TesseractOcrEngine(lang="eng"),
        config=config,
        work_dir=work,
        **kwargs,  # type: ignore[arg-type]
    )


def test_the_conversion_never_touches_the_network(
    sample_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No socket is opened during a local conversion."""

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("the local conversion tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)

    pipeline = _pipeline(sample_pdf, tmp_path / "work")
    result = pipeline.run(BookMetadata(title="El libro"), tmp_path / "book.epub")
    assert result.epub_path.is_file()


def test_two_runs_produce_the_same_epub(sample_pdf: Path, tmp_path: Path) -> None:
    """The conversion is reproducible, byte for byte."""
    first = tmp_path / "first.epub"
    second = tmp_path / "second.epub"
    _pipeline(sample_pdf, tmp_path / "work-1").run(
        BookMetadata(title="El libro", author="Anonimo"), first
    )
    _pipeline(sample_pdf, tmp_path / "work-2").run(
        BookMetadata(title="El libro", author="Anonimo"), second
    )
    # The modification date of the publication is part of the metadata, so
    # only the content documents are compared.
    with zipfile.ZipFile(first) as a, zipfile.ZipFile(second) as b:
        assert sorted(a.namelist()) == sorted(b.namelist())
        for name in a.namelist():
            if name == "EPUB/package.opf":
                continue
            assert a.read(name) == b.read(name), name


def test_the_cache_does_not_change_the_result(sample_pdf: Path, tmp_path: Path) -> None:
    """A cached run gives exactly the same book as an uncached one."""
    cached = tmp_path / "cached.epub"
    fresh = tmp_path / "fresh.epub"
    cache = FileCache(tmp_path / "cache")

    _pipeline(sample_pdf, tmp_path / "work-1", cache=cache).run(
        BookMetadata(title="El libro"), cached
    )
    _pipeline(sample_pdf, tmp_path / "work-2", cache=cache).run(
        BookMetadata(title="El libro"), fresh
    )
    with zipfile.ZipFile(cached) as a, zipfile.ZipFile(fresh) as b:
        assert a.read("EPUB/text/chapter-001.xhtml") == b.read("EPUB/text/chapter-001.xhtml")
