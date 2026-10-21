"""Tests for the Tesseract adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from scan2epub.domain.models import PageImage
from scan2epub.errors import EngineNotAvailableError, OcrError
from scan2epub.infrastructure.ocr.tesseract import (
    TesseractOcrEngine,
    available_languages,
    tesseract_version,
)


def _data() -> dict[str, list[object]]:
    """Build a Tesseract data dictionary with two words in one line."""
    return {
        "level": [1, 5, 5, 5],
        "page_num": [1, 1, 1, 1],
        "block_num": [0, 1, 1, 2],
        "par_num": [0, 1, 1, 1],
        "line_num": [0, 1, 1, 1],
        "word_num": [0, 1, 2, 1],
        "left": [0, 100, 200, 100],
        "top": [0, 500, 500, 700],
        "width": [0, 80, 90, 80],
        "height": [0, 30, 30, 30],
        "conf": [-1, 95.0, 88.0, 60.0],
        "text": ["", "Hola", "mundo", "Adios"],
    }


def test_the_words_are_grouped_into_blocks() -> None:
    """The words of a block become the lines of a text block."""
    engine = TesseractOcrEngine(lang="eng")
    page = PageImage(index=0, path=Path("a.png"), width=1000, height=1000)
    blocks = engine._to_blocks(_data(), page)
    assert len(blocks) == 2
    assert blocks[0].lines == ("Hola mundo",)
    assert blocks[1].lines == ("Adios",)


def test_the_confidence_is_the_average_of_the_words() -> None:
    """The confidence of a block is the mean of its words."""
    engine = TesseractOcrEngine(lang="eng")
    page = PageImage(index=0, path=Path("a.png"), width=1000, height=1000)
    blocks = engine._to_blocks(_data(), page)
    assert blocks[0].confidence == pytest.approx((95.0 + 88.0) / 200)
    assert blocks[1].confidence == pytest.approx(0.60)


def test_the_geometry_is_normalised() -> None:
    """The bounding box of a block is relative to the page."""
    engine = TesseractOcrEngine(lang="eng")
    page = PageImage(index=0, path=Path("a.png"), width=1000, height=1000)
    blocks = engine._to_blocks(_data(), page)
    assert blocks[0].bbox.x0 == pytest.approx(0.1)
    assert blocks[0].bbox.y0 == pytest.approx(0.5)
    assert blocks[0].bbox.x1 == pytest.approx(0.29)
    assert blocks[0].bbox.y1 == pytest.approx(0.53)


def test_the_blocks_are_numbered_in_reading_order() -> None:
    """The order of the blocks follows the reading order."""
    engine = TesseractOcrEngine(lang="eng")
    page = PageImage(index=2, path=Path("a.png"), width=1000, height=1000)
    blocks = engine._to_blocks(_data(), page)
    assert [block.order for block in blocks] == [0, 1]
    assert all(block.page == 2 for block in blocks)


def test_the_empty_words_are_ignored() -> None:
    """A word without characters does not create a block."""
    engine = TesseractOcrEngine(lang="eng")
    page = PageImage(index=0, path=Path("a.png"), width=1000, height=1000)
    data = _data()
    data["text"] = ["", "  ", "mundo", "Adios"]
    blocks = engine._to_blocks(data, page)
    assert blocks[0].lines == ("mundo",)


def test_the_version_is_reported() -> None:
    """The version of Tesseract is available."""
    version = tesseract_version()
    if version is None:
        pytest.skip("Tesseract is not installed")
    assert version


def test_the_languages_are_reported() -> None:
    """The available language data is listed."""
    languages = available_languages()
    if not languages:
        pytest.skip("Tesseract is not installed")
    assert "eng" in languages


def test_a_missing_page_is_reported(tmp_path: Path) -> None:
    """A page that cannot be read is an error."""
    engine = TesseractOcrEngine(lang="eng")
    page = PageImage(index=0, path=tmp_path / "missing.png", width=10, height=10)
    with pytest.raises(OcrError):
        engine.recognize(page)


def test_the_tessdata_directory_is_added_to_the_command() -> None:
    """The language data directory reaches the command line."""
    engine = TesseractOcrEngine(lang="eng", tessdata_dir=Path("/opt/tessdata"))
    config = engine._config()
    assert "--tessdata-dir" in config
    assert "opt" in config
    assert "--oem 1" in config
    assert "--psm 3" in config


def test_the_engine_reports_a_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clear error is raised when Tesseract is not installed."""
    import shutil

    import scan2epub.infrastructure.ocr.tesseract as module

    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    monkeypatch.setattr(module, "_WINDOWS_CANDIDATES", ())
    monkeypatch.setattr(module.pytesseract.pytesseract, "tesseract_cmd", "")
    with pytest.raises(EngineNotAvailableError):
        module.TesseractOcrEngine(lang="eng")
    assert shutil is not None
