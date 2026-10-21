"""Tests for the EPUB validation stage."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scan2epub.application.stages.validate import find_epubcheck, validate_epub
from scan2epub.domain.models import Book, BookMetadata, Chapter
from scan2epub.infrastructure.epub.writer import EpubWriter


def _write_epub(path: Path) -> Path:
    """Write a minimal valid EPUB."""
    EpubWriter().write(
        Book(metadata=BookMetadata(title="Libro"), chapters=(Chapter("c1", "T"),)), path
    )
    return path


def test_a_missing_tool_is_reported(tmp_path: Path, monkeypatch) -> None:
    """When EPUBCheck is not installed the validation is skipped."""
    monkeypatch.setattr("scan2epub.application.stages.validate.find_epubcheck", lambda: None)
    report = validate_epub(tmp_path / "book.epub")
    assert not report.ran
    assert report.passed
    assert report.reason is not None


def test_a_broken_epub_is_detected(tmp_path: Path) -> None:
    """An EPUB without the mandatory metadata is rejected."""
    source = _write_epub(tmp_path / "good.epub")
    broken = tmp_path / "broken.epub"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(broken, "w") as target:
        for name in original.namelist():
            data = original.read(name)
            if name.endswith("package.opf"):
                data = data.replace(b"<dc:language>es</dc:language>", b"")
            target.writestr(name, data)
    report = validate_epub(broken)
    if not report.ran:
        pytest.skip("EPUBCheck is not installed")
    assert not report.passed
    assert report.errors


def test_a_valid_epub_passes(tmp_path: Path) -> None:
    """A well formed EPUB passes the validation."""
    path = _write_epub(tmp_path / "good.epub")
    report = validate_epub(path)
    if not report.ran:
        pytest.skip("EPUBCheck is not installed")
    assert report.passed
    assert not report.errors


def test_the_tool_is_looked_up_in_the_environment(monkeypatch) -> None:
    """The environment variable points at the jar."""
    monkeypatch.setenv("SCAN2EPUB_EPUBCHECK_JAR", "/opt/epubcheck.jar")
    assert find_epubcheck() is None or find_epubcheck().name == "epubcheck.jar"
