"""Tests for the PDF page source."""

from __future__ import annotations

from pathlib import Path

import pytest

from scan2epub.errors import PipelineError
from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource, ink_ratio


def test_the_pages_are_rendered(sample_pdf: Path, tmp_path: Path) -> None:
    """Every page of the PDF becomes a PNG file."""
    source = PdfiumPageSource(sample_pdf, dpi=100, out_dir=tmp_path / "pages")
    pages = source.pages()
    assert len(pages) == 3
    for index, page in enumerate(pages):
        assert page.index == index
        assert page.path.is_file()
        assert page.width > 0 and page.height > 0


def test_the_resolution_is_honoured(sample_pdf: Path, tmp_path: Path) -> None:
    """The requested resolution drives the size of the image."""
    low = PdfiumPageSource(sample_pdf, dpi=72, out_dir=tmp_path / "low").pages()
    high = PdfiumPageSource(sample_pdf, dpi=144, out_dir=tmp_path / "high").pages()
    assert high[0].width == pytest.approx(low[0].width * 2, rel=0.05)
    assert high[0].height == pytest.approx(low[0].height * 2, rel=0.05)


def test_the_number_of_pages_is_reported(sample_pdf: Path) -> None:
    """The page count is known without rendering the document."""
    assert PdfiumPageSource(sample_pdf).page_count() == 3


def test_a_missing_file_is_reported(tmp_path: Path) -> None:
    """A file that does not exist is an error."""
    with pytest.raises(PipelineError):
        PdfiumPageSource(tmp_path / "missing.pdf")


def test_a_file_that_is_not_a_pdf_is_reported(tmp_path: Path) -> None:
    """A file that is not a PDF is an error."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a PDF")
    with pytest.raises(PipelineError):
        PdfiumPageSource(broken).pages()


def test_a_blank_page_is_detected(tmp_path: Path) -> None:
    """A page without ink is marked as blank."""
    from PIL import Image

    path = tmp_path / "blank.png"
    Image.new("L", (400, 600), 250).save(path)
    assert ink_ratio(Image.open(path)) < 0.01


def test_a_page_with_text_is_not_blank(tmp_path: Path) -> None:
    """A page with ink is not blank."""
    from PIL import Image, ImageDraw

    image = Image.new("L", (400, 600), 245)
    draw = ImageDraw.Draw(image)
    for index in range(10):
        draw.line([(40, 40 + index * 40), (360, 40 + index * 40)], fill=20, width=4)
    path = tmp_path / "text.png"
    image.save(path)
    assert ink_ratio(Image.open(path)) > 0.01
