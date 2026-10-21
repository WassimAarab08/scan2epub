"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if sys.version_info >= (3, 13):
    pass
else:  # pragma: no cover - Python 3.12 ships tomllib as well
    pass

from tests.fixtures import make_scanned_image, make_text_pdf

if TYPE_CHECKING:
    from scan2epub.domain.models import PageContent

TESTS_DIR = Path(__file__).parent
PROJECT_ROOT = TESTS_DIR.parent


def _autodiscover_epubcheck() -> None:
    """Point EPUBCheck at the local installation when there is one."""
    import os

    if os.environ.get("SCAN2EPUB_EPUBCHECK_JAR"):
        return
    cache = Path.home() / ".cache" / "scan2epub"
    if not cache.is_dir():
        return
    for jar in sorted(cache.glob("epubcheck*/epubcheck.jar")):
        os.environ["SCAN2EPUB_EPUBCHECK_JAR"] = str(jar)
        return


_autodiscover_epubcheck()


@pytest.fixture
def project_root() -> Path:
    """Return the root of the repository."""
    return PROJECT_ROOT


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Return a synthetic three-page book."""
    return make_text_pdf(tmp_path / "sample.pdf", pages=3)


@pytest.fixture
def require_tesseract() -> None:
    """Skip the test when Tesseract is not installed."""
    from scan2epub.infrastructure.ocr.tesseract import tesseract_version

    if tesseract_version() is None:
        pytest.skip("Tesseract is not installed")


@pytest.fixture
def scanned_image(tmp_path: Path) -> Path | None:
    """Return a degraded scan-like image, or ``None`` without a system font."""
    return make_scanned_image(tmp_path / "scan.png")


@pytest.fixture
def pages() -> list[PageContent]:
    """Return a small set of recognised pages used by the cleaning tests."""
    from scan2epub.domain.models import BBox, BlockKind, PageContent, TextBlock

    def block(
        text: str,
        top: float,
        bottom: float,
        *,
        order: int,
        page: int,
        kind: BlockKind = BlockKind.BODY,
    ) -> TextBlock:
        return TextBlock(
            lines=tuple(text.split("\n")),
            bbox=BBox(0.1, top, 0.9, bottom),
            confidence=0.95,
            kind=kind,
            order=order,
            page=page,
        )

    return [
        PageContent(
            index=0,
            blocks=(
                block("HISTORIA DE LA IMPRENTA", 0.02, 0.06, order=0, page=0),
                block("CAPITULO PRIMERO", 0.12, 0.17, order=1, page=0),
                block(
                    "El hombre que escribe con la letra larga, llamada por los\n"
                    "impresores letra sigma, Towards did not know that the s final",
                    0.2,
                    0.32,
                    order=2,
                    page=0,
                ),
                block("— 42 —", 0.93, 0.97, order=3, page=0),
            ),
        ),
        PageContent(
            index=1,
            blocks=(
                block("HISTORIA DE LA IMPRENTA", 0.02, 0.06, order=0, page=1),
                block(
                    "de la palabra se escribia de otra manera que la inicial.",
                    0.2,
                    0.26,
                    order=1,
                    page=1,
                ),
                block(
                    "1 Nota del autor sobre la imprenta y sus costes.", 0.86, 0.9, order=2, page=1
                ),
                block("— 43 —", 0.93, 0.97, order=3, page=1),
            ),
        ),
        PageContent(
            index=2,
            blocks=(
                block("HISTORIA DE LA IMPRENTA", 0.02, 0.06, order=0, page=2),
                block(
                    "Y por esta razon los lectores modernos encuentran estas",
                    0.2,
                    0.26,
                    order=1,
                    page=2,
                ),
                block("— 44 —", 0.93, 0.97, order=2, page=2),
            ),
        ),
    ]
