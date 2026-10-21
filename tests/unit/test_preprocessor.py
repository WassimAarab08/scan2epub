"""Tests for the image pre-processing."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from scan2epub.config import PreprocessConfig
from scan2epub.domain.models import PageImage
from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor, estimate_skew


def _page(path: Path) -> PageImage:
    """Build a page descriptor for an image on disk."""
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert image is not None
    return PageImage(
        index=0,
        path=path,
        width=image.shape[1],
        height=image.shape[0],
    )


def _write_text_image(path: Path, *, angle: float = 0.0, border: int = 0) -> Path:
    """Render a page with horizontal lines of text."""
    width, height = 900, 1200
    image = np.full((height, width), 245, dtype=np.uint8)
    for index in range(20):
        top = 120 + index * 50
        cv2.line(image, (100, top), (800, top), 30, 3)
    if border:
        cv2.rectangle(image, (0, 0), (width - 1, height - 1), 10, border)
    if angle:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        image = cv2.warpAffine(
            image, matrix, (width, height), borderMode=cv2.BORDER_CONSTANT, borderValue=245
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    return path


def test_a_straight_page_has_no_skew(tmp_path: Path) -> None:
    """A page that is already straight is not rotated."""
    path = _write_text_image(tmp_path / "straight.png")
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    assert abs(estimate_skew(gray)) < 0.5


def test_a_skewed_page_is_detected(tmp_path: Path) -> None:
    """The skew of a tilted page is measured."""
    path = _write_text_image(tmp_path / "skewed.png", angle=3.0)
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    assert abs(estimate_skew(gray)) > 1.0


def test_the_preprocessor_reduces_the_skew(tmp_path: Path) -> None:
    """The deskew step makes the text lines horizontal again."""
    path = _write_text_image(tmp_path / "skewed.png", angle=3.0)
    page = _page(path)
    result = OpenCvPreprocessor(PreprocessConfig(crop_borders=False, binarize=False)).process(
        page, tmp_path / "out"
    )
    gray = cv2.imread(str(result.path), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    assert abs(estimate_skew(gray)) < 1.0


def test_the_borders_are_cropped(tmp_path: Path) -> None:
    """The dark frame of a scan is removed."""
    path = _write_text_image(tmp_path / "bordered.png", border=25)
    page = _page(path)
    result = OpenCvPreprocessor(PreprocessConfig()).process(page, tmp_path / "out")
    assert result.width < page.width
    assert result.height < page.height


def test_the_output_is_binary(tmp_path: Path) -> None:
    """The binarisation leaves only black and white pixels."""
    path = _write_text_image(tmp_path / "page.png")
    page = _page(path)
    result = OpenCvPreprocessor(PreprocessConfig(binarize=True)).process(page, tmp_path / "out")
    gray = cv2.imread(str(result.path), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    assert set(np.unique(gray)).issubset({0, 255})


def test_the_output_is_written_to_disk(tmp_path: Path) -> None:
    """The processed page is a file on disk."""
    path = _write_text_image(tmp_path / "page.png")
    page = _page(path)
    out = tmp_path / "out"
    result = OpenCvPreprocessor(PreprocessConfig()).process(page, out)
    assert result.path.is_file()
    assert result.path.parent == out
    assert result.width > 0 and result.height > 0


def test_a_missing_file_is_reported(tmp_path: Path) -> None:
    """A page that cannot be read is an error."""
    page = PageImage(index=0, path=tmp_path / "missing.png", width=10, height=10)
    with pytest.raises(ValueError):
        OpenCvPreprocessor().process(page, tmp_path / "out")
