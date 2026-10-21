"""EPUB 3 writer.

The EPUB is assembled by hand: a ZIP container with a stored ``mimetype``
entry, a ``META-INF/container.xml``, an OPF package document, a navigation
document and one XHTML content document per chapter.

Two rules drive the markup:

* The stylesheet never sets a font family, a font size, a line height or the
  body margin, so the reading preferences of the e-reader always win.
* Every piece of text coming from the OCR is XML-escaped. No user content is
  ever interpreted as markup.
"""

from __future__ import annotations

import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from scan2epub.domain.models import BlockKind, Book, Chapter, Figure

__all__ = ["EpubResult", "EpubWriter"]

#: Namespace of the fixed timestamps written into the ZIP, for reproducibility.
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

#: The UUID namespace used to derive a stable publication identifier.
_UUID_NAMESPACE = uuid.UUID("6f2b0e1c-2c0a-5f3e-9c4a-2d5b6e8f1a70")

_STYLESHEET = """\
/* scan2epub - deliberately minimal stylesheet.
 *
 * The typography of the book (typeface, size, leading and margins) is never
 * declared here: the reading preferences of the e-reader always win.
 */
p {
  text-indent: 1em;
}
p.first {
  text-indent: 0;
}
h1, h2, h3, h4 {
  text-align: center;
  page-break-after: avoid;
  break-after: avoid;
}
h1 {
  page-break-before: always;
  break-before: page;
}
blockquote {
  margin-left: 2em;
  margin-right: 2em;
}
img {
  max-width: 100%;
  height: auto;
}
hr {
  width: 30%;
  margin: 1em auto;
  border: 0;
  border-top: 1px solid currentColor;
}
aside {
  page-break-inside: avoid;
  break-inside: avoid;
}
"""

_CONTAINER_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_FOOTNOTE_MARKER_RE = re.compile(
    r"^\s*[\(\[]?([0-9]{1,3}|[ivxlcdm]{1,7})[\)\].:]?\s+", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class EpubResult:
    """The outcome of writing an EPUB."""

    path: Path
    size: int
    chapters: int
    figures: int
    manifest_items: int


@dataclass(frozen=True, slots=True)
class _Note:
    """A footnote collected from a page."""

    marker: str
    text: str
    full_text: str
    anchor: str
    page: int


@dataclass(frozen=True, slots=True)
class _Heading:
    """A heading inside a chapter."""

    level: int
    title: str
    anchor: str


@dataclass(frozen=True, slots=True)
class _ChapterPlan:
    """Everything needed to render one chapter document."""

    chapter: Chapter
    file_name: str
    headings: tuple[_Heading, ...]


def _escape(text: str) -> str:
    """Escape a text run for XML."""
    return escape(text)


class EpubWriter:
    """Write a :class:`~scan2epub.domain.models.Book` as an EPUB 3 file."""

    def __init__(self, *, identifier: str | None = None, language: str = "es") -> None:
        """Initialise the writer.

        Args:
            identifier: A stable identifier for the publication. When omitted
                a deterministic UUID is derived from the title and author.
            language: The default language of the publication.
        """
        self.identifier = identifier
        self.language = language

    # -- public API ----------------------------------------------------

    def write(self, book: Book, out_path: Path) -> EpubResult:
        """Write ``book`` to ``out_path``.

        Args:
            book: The structured book.
            out_path: The destination ``.epub`` file.

        Returns:
            A summary of what was written.
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        plans = self._plan_chapters(book)
        figures = self._plan_figures(book)

        package_id = self.identifier or self._derive_identifier(book)
        modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        entries: list[tuple[str, str]] = [
            ("META-INF/container.xml", _CONTAINER_XML),
            (
                "EPUB/package.opf",
                self._package_document(book, plans, figures, package_id, modified),
            ),
            ("EPUB/nav.xhtml", self._nav_document(book, plans)),
            ("EPUB/styles/main.css", _STYLESHEET),
        ]
        for plan in plans:
            entries.append((f"EPUB/text/{plan.file_name}", self._chapter_document(book, plan)))

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            # The mimetype entry must come first and must be stored uncompressed.
            info = zipfile.ZipInfo("mimetype", date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, "application/epub+zip")

            for name, payload in entries:
                info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, payload.encode("utf-8"))

            for figure in book.figures:
                if not figure.path.is_file():
                    continue
                info = zipfile.ZipInfo(
                    f"EPUB/images/{figure.id}{figure.path.suffix.lower()}",
                    date_time=_ZIP_TIMESTAMP,
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, figure.path.read_bytes())

        return EpubResult(
            path=out_path,
            size=out_path.stat().st_size,
            chapters=len(plans),
            figures=len(book.figures),
            manifest_items=len(entries) + len(book.figures),
        )

    # -- planning -------------------------------------------------------

    def _plan_chapters(self, book: Book) -> tuple[_ChapterPlan, ...]:
        """Build the per-chapter rendering plan."""
        chapters = book.chapters or (
            Chapter(id="body", title=book.metadata.title, level=1, start_page=0, end_page=0),
        )
        plans: list[_ChapterPlan] = []
        for index, chapter in enumerate(chapters, start=1):
            headings: list[_Heading] = []
            for block in chapter.blocks:
                if block.kind is not BlockKind.HEADING:
                    continue
                title = " ".join(block.text.split())
                if not title:
                    continue
                headings.append(
                    _Heading(
                        level=min(4, max(2, block.level or 2)),
                        title=title,
                        anchor=f"{chapter.id}-h{len(headings) + 1}",
                    )
                )
            plans.append(
                _ChapterPlan(
                    chapter=chapter,
                    file_name=f"chapter-{index:03d}.xhtml",
                    headings=tuple(headings),
                )
            )
        return tuple(plans)

    def _plan_figures(self, book: Book) -> dict[str, Figure]:
        """Index the figures by the identifier used in the manifest."""
        return {figure.id: figure for figure in book.figures}

    def _derive_identifier(self, book: Book) -> str:
        """Return a deterministic publication identifier."""
        seed = f"{book.metadata.title}|{book.metadata.author}|{book.metadata.language}"
        return f"urn:uuid:{uuid.uuid5(_UUID_NAMESPACE, seed)}"

    # -- documents ------------------------------------------------------

    def _package_document(
        self,
        book: Book,
        plans: tuple[_ChapterPlan, ...],
        figures: dict[str, Figure],
        package_id: str,
        modified: str,
    ) -> str:
        """Render the OPF package document."""
        metadata = book.metadata
        language = metadata.language or self.language

        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"',
            f'         unique-identifier="pub-id" xml:lang={quoteattr(language)}>',
            '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
            f'    <dc:identifier id="pub-id">{_escape(package_id)}</dc:identifier>',
            f"    <dc:title>{_escape(metadata.title)}</dc:title>",
            f"    <dc:language>{_escape(language)}</dc:language>",
        ]
        if metadata.author:
            lines.append(f'    <dc:creator id="creator">{_escape(metadata.author)}</dc:creator>')
            lines.append(
                '    <meta refines="#creator" property="role" scheme="marc:relators">aut</meta>'
            )
        if metadata.year:
            lines.append(f"    <dc:date>{_escape(metadata.year)}</dc:date>")
        if metadata.publisher:
            lines.append(f"    <dc:publisher>{_escape(metadata.publisher)}</dc:publisher>")
        if metadata.description:
            lines.append(f"    <dc:description>{_escape(metadata.description)}</dc:description>")
        if metadata.subject:
            lines.append(f"    <dc:subject>{_escape(metadata.subject)}</dc:subject>")
        lines.append(f'    <meta property="dcterms:modified">{modified}</meta>')
        lines.append("  </metadata>")

        lines.append("  <manifest>")
        lines.append(
            '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
            ' properties="nav"/>'
        )
        lines.append('    <item id="css" href="styles/main.css" media-type="text/css"/>')
        for plan in plans:
            lines.append(
                f'    <item id="{plan.chapter.id}" href="text/{plan.file_name}"'
                ' media-type="application/xhtml+xml"/>'
            )
        for figure_id, figure in figures.items():
            suffix = figure.path.suffix.lower() or ".png"
            media_type = _MEDIA_TYPES.get(suffix, "image/png")
            lines.append(
                f'    <item id="{figure_id}" href="images/{figure_id}{suffix}"'
                f' media-type="{media_type}"/>'
            )
        lines.append("  </manifest>")

        lines.append("  <spine>")
        for plan in plans:
            lines.append(f'    <itemref idref="{plan.chapter.id}"/>')
        lines.append("  </spine>")
        lines.append("</package>")
        return "\n".join(lines) + "\n"

    def _nav_document(self, book: Book, plans: tuple[_ChapterPlan, ...]) -> str:
        """Render the EPUB 3 navigation document."""
        language = book.metadata.language or self.language
        toc_title, landmarks_title = _NAV_LABELS.get(
            language.split("-")[0].lower(), ("Table of contents", "Landmarks")
        )
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            "<!DOCTYPE html>",
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"',
            f"      lang={quoteattr(language)} xml:lang={quoteattr(language)}>",
            "  <head>",
            '    <meta charset="utf-8"/>',
            f"    <title>{_escape(toc_title)}</title>",
            '    <link rel="stylesheet" type="text/css" href="styles/main.css"/>',
            "  </head>",
            "  <body>",
            '    <nav epub:type="toc" id="toc">',
            f"      <h1>{_escape(toc_title)}</h1>",
            "      <ol>",
        ]
        for plan in plans:
            title = " ".join(plan.chapter.title.split()) or "Sin título"
            lines.append(f'        <li><a href="text/{plan.file_name}">{_escape(title)}</a>')
            if plan.headings:
                lines.append("          <ol>")
                for heading in plan.headings:
                    lines.append(
                        f'            <li><a href="text/{plan.file_name}#{heading.anchor}">'
                        f"{_escape(heading.title)}</a></li>"
                    )
                lines.append("          </ol>")
            lines.append("        </li>")
        lines.append("      </ol>")
        lines.append("    </nav>")
        lines.append('    <nav epub:type="landmarks" id="landmarks" hidden="hidden">')
        lines.append(f"      <h1>{_escape(landmarks_title)}</h1>")
        lines.append("      <ol>")
        if plans:
            first = plans[0]
            start_label = _NAV_LABELS.get(language.split("-")[0].lower(), ("Table of contents",))[0]
            lines.append(
                f'        <li><a epub:type="bodymatter" href="text/{first.file_name}">'
                f"{_escape(start_label)}</a></li>"
            )
        for plan in plans:
            title = " ".join(plan.chapter.title.split()) or "Sin título"
            lines.append(
                f'        <li><a epub:type="chapter" href="text/{plan.file_name}">'
                f"{_escape(title)}</a></li>"
            )
        lines.append("      </ol>")
        lines.append("    </nav>")
        lines.append("  </body>")
        lines.append("</html>")
        return "\n".join(lines) + "\n"

    def _chapter_document(self, book: Book, plan: _ChapterPlan) -> str:
        """Render one chapter as an XHTML content document."""
        chapter = plan.chapter
        language = book.metadata.language or self.language
        title = " ".join(chapter.title.split()) or "Sin título"

        notes = self._collect_notes(chapter)
        note_by_page: dict[int, list[_Note]] = {}
        for note in notes:
            note_by_page.setdefault(note.page, []).append(note)

        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            "<!DOCTYPE html>",
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"',
            f"      lang={quoteattr(language)} xml:lang={quoteattr(language)}>",
            "  <head>",
            f"    <title>{_escape(title)}</title>",
            '    <link rel="stylesheet" type="text/css" href="../styles/main.css"/>',
            "  </head>",
            "  <body>",
            f'    <section epub:type="chapter" id="{chapter.id}">',
            f"      <h1>{_escape(title)}</h1>",
        ]

        used_notes: dict[str, _Note] = {}
        first_paragraph = True
        heading_index = 0
        for block in chapter.blocks:
            if block.kind is BlockKind.FOOTNOTE:
                continue
            text = " ".join(block.text.split())
            if not text:
                continue
            if block.kind is BlockKind.HEADING:
                anchor = f"{chapter.id}-h{heading_index + 1}"
                heading_index += 1
                level = min(4, max(2, block.level or 2))
                lines.append(f'      <h{level} id="{anchor}">{_escape(text)}</h{level}>')
                first_paragraph = True
                continue

            candidates = note_by_page.get(block.page, [])
            html, _matched = self._link_notes(text, candidates, used_notes)
            css_class = ' class="first"' if first_paragraph else ""
            lines.append(f"      <p{css_class}>{html}</p>")
            first_paragraph = False

        if notes:
            lines.append("      <hr/>")
            for note in notes:
                if note.anchor in used_notes:
                    lines.append(
                        f'      <aside epub:type="footnote" id="{note.anchor}">'
                        f"<p>{_escape(note.text)}</p></aside>"
                    )
                else:
                    # No reference could be placed in the body text: keep the
                    # note as a plain paragraph, with its number, so that the
                    # document stays symmetric.
                    lines.append(f"      <p>{_escape(note.full_text)}</p>")

        lines.append("    </section>")
        lines.append("  </body>")
        lines.append("</html>")
        return "\n".join(lines) + "\n"

    def _collect_notes(self, chapter: Chapter) -> list[_Note]:
        """Extract the footnotes of a chapter.

        The identifier of a note is the position of the note in the chapter,
        never its number: a book that numbers its notes again on every page
        would otherwise produce duplicate identifiers, and duplicate
        identifiers are invalid XML.
        """
        notes: list[_Note] = []
        for block in chapter.blocks:
            if block.kind is not BlockKind.FOOTNOTE:
                continue
            raw = " ".join(block.text.split())
            if not raw:
                continue
            match = _FOOTNOTE_MARKER_RE.match(raw)
            if match is None:
                continue
            marker = match.group(1)
            text = raw[match.end() :].strip() or raw
            notes.append(
                _Note(
                    marker=marker,
                    text=text,
                    full_text=raw,
                    anchor=f"{chapter.id}-fn-{len(notes) + 1}",
                    page=block.page,
                )
            )
        return notes

    def _link_notes(
        self,
        text: str,
        candidates: list[_Note],
        used: dict[str, _Note],
    ) -> tuple[str, bool]:
        """Insert noteref links for the footnotes whose marker is in ``text``."""
        insertions: list[tuple[int, int, str]] = []
        for note in candidates:
            if note.anchor in used:
                continue
            pattern = re.compile(rf"(?<![\w]){re.escape(note.marker)}(?![\w])")
            match = pattern.search(text)
            if match is None:
                continue
            link = (
                f'<sup><a epub:type="noteref" href="#{note.anchor}">'
                f"{_escape(note.marker)}</a></sup>"
            )
            insertions.append((match.start(), match.end(), link))
            used[note.anchor] = note
        if not insertions:
            return _escape(text), False
        insertions.sort()
        chunks: list[str] = []
        cursor = 0
        for start, end, link in insertions:
            chunks.append(_escape(text[cursor:start]))
            chunks.append(link)
            cursor = end
        chunks.append(_escape(text[cursor:]))
        return "".join(chunks), True


_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}

#: The labels of the navigation document, per language.
_NAV_LABELS: dict[str, tuple[str, str]] = {
    "es": ("Índice", "Marcadores"),
    "en": ("Table of contents", "Landmarks"),
    "fr": ("Table des matières", "Repères"),
    "de": ("Inhaltsverzeichnis", "Lesezeichen"),
    "it": ("Indice", "Segnalibri"),
    "pt": ("Índice", "Marcadores"),
    "ca": ("Índex", "Marcadors"),
    "gl": ("Índice", "Marcadores"),
    "nl": ("Inhoudsopgave", "Bladwijzers"),
}
