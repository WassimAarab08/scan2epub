"""Tests for the hand-written EPUB 3 writer."""

from __future__ import annotations

import zipfile
from pathlib import Path

from scan2epub.domain.models import (
    BBox,
    BlockKind,
    Book,
    BookMetadata,
    Chapter,
    Figure,
    TextBlock,
)
from scan2epub.infrastructure.epub.writer import EpubWriter


def _block(
    text: str,
    *,
    top: float = 0.2,
    bottom: float = 0.3,
    order: int = 0,
    page: int = 0,
    kind: BlockKind = BlockKind.BODY,
    level: int = 0,
) -> TextBlock:
    """Build a text block with the given geometry."""
    return TextBlock(
        lines=tuple(text.split("\n")),
        bbox=BBox(0.1, top, 0.9, bottom),
        confidence=0.9,
        kind=kind,
        order=order,
        page=page,
        level=level,
    )


def _book(*chapters: Chapter, title: str = "Libro de prueba") -> Book:
    """Build a book with the given chapters."""
    return Book(
        metadata=BookMetadata(title=title, author="Autor", language="es", year="1765"),
        chapters=chapters,
        pages=(),
    )


def _read(archive: zipfile.ZipFile, name: str) -> str:
    """Read a member of the archive as UTF-8 text."""
    return archive.read(name).decode("utf-8")


def test_the_mimetype_is_the_first_entry_and_is_stored(tmp_path: Path) -> None:
    """The EPUB container follows the specification."""
    target = tmp_path / "book.epub"
    EpubWriter().write(_book(), target)
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert names[0] == "mimetype"
        info = archive.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"


def test_the_container_points_at_the_package(tmp_path: Path) -> None:
    """``META-INF/container.xml`` references the OPF file."""
    target = tmp_path / "book.epub"
    EpubWriter().write(_book(), target)
    with zipfile.ZipFile(target) as archive:
        container = _read(archive, "META-INF/container.xml")
    assert "EPUB/package.opf" in container
    assert "application/oebps-package+xml" in container


def test_the_package_declares_the_mandatory_metadata(tmp_path: Path) -> None:
    """EPUB 3 requires an identifier, a title, a language and a date."""
    target = tmp_path / "book.epub"
    EpubWriter().write(_book(), target)
    with zipfile.ZipFile(target) as archive:
        package = _read(archive, "EPUB/package.opf")
    assert 'version="3.0"' in package
    assert "<dc:title>Libro de prueba</dc:title>" in package
    assert "<dc:language>es</dc:language>" in package
    assert "<dc:creator" in package
    assert 'property="dcterms:modified"' in package
    assert 'properties="nav"' in package


def test_the_navigation_document_lists_the_chapters(tmp_path: Path) -> None:
    """The navigation document is a real EPUB 3 nav."""
    target = tmp_path / "book.epub"
    book = _book(
        Chapter(id="chapter-1", title="CAPITULO PRIMERO", blocks=(_block("Texto."),)),
        Chapter(id="chapter-2", title="CAPITULO SEGUNDO", blocks=(_block("Texto."),)),
    )
    EpubWriter().write(book, target)
    with zipfile.ZipFile(target) as archive:
        nav = _read(archive, "EPUB/nav.xhtml")
    assert 'epub:type="toc"' in nav
    assert "CAPITULO PRIMERO" in nav
    assert 'href="text/chapter-002.xhtml"' in nav


def test_the_stylesheet_does_not_force_the_typography(tmp_path: Path) -> None:
    """The reader preferences always win."""
    target = tmp_path / "book.epub"
    EpubWriter().write(_book(), target)
    with zipfile.ZipFile(target) as archive:
        stylesheet = _read(archive, "EPUB/styles/main.css")
    for property_name in ("font-family", "font-size", "line-height"):
        assert f"{property_name}:" not in stylesheet
    # The margins of the page are never touched either.
    assert "body {" not in stylesheet
    assert "margin: 0" not in stylesheet


def test_the_text_is_escaped(tmp_path: Path) -> None:
    """A text that looks like markup is escaped."""
    target = tmp_path / "book.epub"
    book = _book(
        Chapter(
            id="chapter-1",
            title="Titulo",
            blocks=(_block("<script>alert('x')</script> & mas"),),
        )
    )
    EpubWriter().write(book, target)
    with zipfile.ZipFile(target) as archive:
        document = _read(archive, "EPUB/text/chapter-001.xhtml")
    assert "<script>" not in document
    assert "&lt;script&gt;" in document
    assert "&amp;" in document


def test_a_footnote_becomes_a_linked_note(tmp_path: Path) -> None:
    """A footnote with a marker in the body becomes a real EPUB note."""
    target = tmp_path / "book.epub"
    book = _book(
        Chapter(
            id="chapter-1",
            title="Titulo",
            blocks=(
                _block("El texto principal 1 y su continuacion.", order=0, page=0),
                _block("1 Nota del autor.", order=1, page=0, kind=BlockKind.FOOTNOTE),
            ),
        )
    )
    EpubWriter().write(book, target)
    with zipfile.ZipFile(target) as archive:
        document = _read(archive, "EPUB/text/chapter-001.xhtml")
    assert 'epub:type="noteref"' in document
    assert 'epub:type="footnote"' in document
    assert 'href="#chapter-1-fn-1"' in document


def test_a_footnote_without_a_marker_stays_a_paragraph(tmp_path: Path) -> None:
    """A note that cannot be referenced is kept as plain text."""
    target = tmp_path / "book.epub"
    book = _book(
        Chapter(
            id="chapter-1",
            title="Titulo",
            blocks=(
                _block("El texto principal y su continuacion.", order=0, page=0),
                _block("1 Nota del autor.", order=1, page=0, kind=BlockKind.FOOTNOTE),
            ),
        )
    )
    EpubWriter().write(book, target)
    with zipfile.ZipFile(target) as archive:
        document = _read(archive, "EPUB/text/chapter-001.xhtml")
    assert 'epub:type="noteref"' not in document
    assert "Nota del autor." in document


def test_the_notes_sit_in_a_section_of_their_own(tmp_path: Path) -> None:
    """The notes are set apart, under a title in the language of the book."""
    target = tmp_path / "book.epub"
    book = _book(
        Chapter(
            id="chapter-1",
            title="Titulo",
            blocks=(
                _block("El texto principal y su continuacion.", order=0, page=0),
                _block("1 Nota del autor.", order=1, page=0, kind=BlockKind.FOOTNOTE),
            ),
        )
    )
    EpubWriter().write(book, target)
    with zipfile.ZipFile(target) as archive:
        document = _read(archive, "EPUB/text/chapter-001.xhtml")
    assert 'epub:type="endnotes"' in document
    assert ">Notas<" in document


def test_the_headings_of_a_chapter_are_navigable(tmp_path: Path) -> None:
    """A section heading appears in the table of contents."""
    target = tmp_path / "book.epub"
    book = _book(
        Chapter(
            id="chapter-1",
            title="CAPITULO PRIMERO",
            blocks=(
                _block(
                    "De la antigüedad",
                    order=0,
                    kind=BlockKind.HEADING,
                    level=2,
                ),
                _block("El texto.", order=1),
            ),
        )
    )
    EpubWriter().write(book, target)
    with zipfile.ZipFile(target) as archive:
        nav = _read(archive, "EPUB/nav.xhtml")
        document = _read(archive, "EPUB/text/chapter-001.xhtml")
    assert "#chapter-1-h1" in nav
    assert '<h2 id="chapter-1-h1">De la antigüedad</h2>' in document


def test_the_figures_are_included(tmp_path: Path) -> None:
    """The illustrations are copied into the archive."""
    image = tmp_path / "figure.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    target = tmp_path / "book.epub"
    book = Book(
        metadata=BookMetadata(title="Libro"),
        chapters=(Chapter(id="chapter-1", title="Titulo"),),
        figures=(Figure(id="fig-1", page=0, path=image),),
    )
    result = EpubWriter().write(book, target)
    assert result.figures == 1
    with zipfile.ZipFile(target) as archive:
        assert "EPUB/images/fig-1.png" in archive.namelist()
        assert 'media-type="image/png"' in _read(archive, "EPUB/package.opf")


def test_the_output_is_reproducible(tmp_path: Path) -> None:
    """Two runs of the writer produce the same bytes."""
    first = tmp_path / "a.epub"
    second = tmp_path / "b.epub"
    book = _book(Chapter(id="chapter-1", title="Titulo", blocks=(_block("Texto."),)))
    EpubWriter().write(book, first)
    EpubWriter().write(book, second)
    assert first.read_bytes() == second.read_bytes()


def test_a_book_without_chapters_still_produces_a_valid_container(tmp_path: Path) -> None:
    """An empty book still gets a content document."""
    target = tmp_path / "book.epub"
    result = EpubWriter().write(Book(metadata=BookMetadata(title="Vacio")), target)
    assert result.chapters == 1
    with zipfile.ZipFile(target) as archive:
        assert "EPUB/text/chapter-001.xhtml" in archive.namelist()
