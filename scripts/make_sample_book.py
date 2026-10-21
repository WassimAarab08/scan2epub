#!/usr/bin/env python
"""Build a book from the synthetic sample and write it to disk.

The script is used by the continuous integration to produce a real EPUB file
that EPUBCheck then validates.

Usage::

    uv run python scripts/make_sample_book.py --output sample.epub
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    """Build the book."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="sample.epub", help="The destination file.")
    parser.add_argument("--pages", type=int, default=3, help="The number of pages.")
    parser.add_argument("--lang", default="eng", help="The language of the OCR engine.")
    arguments = parser.parse_args()

    from tests.fixtures import make_text_pdf

    from scan2epub.application.pipeline import Pipeline
    from scan2epub.config import Config, GeneralConfig
    from scan2epub.domain.models import BookMetadata
    from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
    from scan2epub.infrastructure.ocr.tesseract import TesseractOcrEngine
    from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource

    work = Path("build") / "sample"
    work.mkdir(parents=True, exist_ok=True)
    source = make_text_pdf(work / "sample.pdf", pages=arguments.pages)

    config = Config(general=GeneralConfig(language=arguments.lang, validate_epub=False))
    pipeline = Pipeline(
        source=PdfiumPageSource(source, dpi=300),
        preprocessor=OpenCvPreprocessor(config.preprocess),
        ocr=TesseractOcrEngine(lang=arguments.lang),
        config=config,
        work_dir=work / "work",
    )
    output = Path(arguments.output)
    result = pipeline.run(
        BookMetadata(title="El libro de prueba", author="Anónimo", language="es"),
        output,
    )
    print(f"written: {output} ({result.epub_size} bytes, {result.page_count} pages)")
    print(f"chapters: {len(result.book.chapters)}")
    print(f"removed running heads: {result.clean.removed_running_heads}")
    print(f"rejoined hyphenations: {result.clean.joined_hyphens}")
    print(f"merged paragraphs: {result.clean.merged_paragraphs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
